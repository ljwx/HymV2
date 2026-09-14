from __future__ import annotations

import math
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from hym.core.models import ImageMatch, Observation, OcrText, Point, Rect, UiNode
from hym.core.ports import ImageMatcherPort, OcrEnginePort, RandomPort
from hym.core.targets import (
    LocatorKind,
    LocatorSpec,
    ResolveAttempt,
    ResolveResult,
    ResolveStatus,
    ResolvedTarget,
    TargetSpec,
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    point: Point
    bounds: Rect | None
    confidence: float
    evidence: str
    metadata: Mapping[str, Any]


class HybridLocator:
    """按目标配置逐级定位，并记住每台设备上次成功的策略。"""

    def __init__(
        self,
        random_source: RandomPort,
        *,
        ocr_engine: OcrEnginePort | None = None,
        image_matcher: ImageMatcherPort | None = None,
    ) -> None:
        self._random = random_source
        self._ocr = ocr_engine
        self._images = image_matcher
        self._last_good: dict[tuple[str, str], str] = {}
        self._ocr_cache: dict[tuple[str, Rect | None], tuple[OcrText, ...]] = {}
        self._image_cache: dict[tuple[str, str, Rect | None], tuple[ImageMatch, ...]] = {}

    def supports(self, kind: LocatorKind) -> bool:
        if kind is LocatorKind.OCR_TEXT:
            return self._ocr is not None
        if kind is LocatorKind.IMAGE:
            return self._images is not None
        return True

    def resolve(self, target: TargetSpec, observation: Observation) -> ResolveResult:
        attempts: list[ResolveAttempt] = []
        key = (observation.device_id, target.target_id)
        locators = sorted(
            target.locators,
            key=lambda item: (item.strategy_id != self._last_good.get(key), item.priority),
        )

        for locator in locators:
            started = perf_counter()
            try:
                candidates = self._resolve_locator(locator, observation)
                candidates = [item for item in candidates if item.confidence >= locator.min_confidence]
                if not candidates:
                    attempts.append(
                        ResolveAttempt(
                            locator.strategy_id,
                            ResolveStatus.NOT_FOUND,
                            perf_counter() - started,
                            "未找到符合条件的目标",
                        )
                    )
                    continue
                selected = self._select(candidates, locator)
                attempts.append(
                    ResolveAttempt(
                        locator.strategy_id,
                        ResolveStatus.FOUND,
                        perf_counter() - started,
                        confidence=selected.confidence,
                    )
                )
                self._last_good[key] = locator.strategy_id
                return ResolveResult(
                    ResolveStatus.FOUND,
                    ResolvedTarget(
                        target_id=target.target_id,
                        strategy_id=locator.strategy_id,
                        point=selected.point,
                        confidence=selected.confidence,
                        observation_id=observation.observation_id,
                        bounds=selected.bounds,
                        evidence=selected.evidence,
                        metadata=selected.metadata,
                    ),
                    tuple(attempts),
                )
            except Exception as error:
                attempts.append(
                    ResolveAttempt(
                        locator.strategy_id,
                        ResolveStatus.ERROR,
                        perf_counter() - started,
                        f"定位策略异常: {error}",
                    )
                )
        return ResolveResult(ResolveStatus.NOT_FOUND, attempts=tuple(attempts), message="未定位到目标")

    def _resolve_locator(self, locator: LocatorSpec, observation: Observation) -> list[_Candidate]:
        if locator.kind is LocatorKind.ACTIVITY:
            return self._activity_candidates(locator, observation)
        if locator.kind in {
            LocatorKind.UI_ID,
            LocatorKind.UI_TEXT,
            LocatorKind.UI_DESC,
            LocatorKind.UI_REGEX,
            LocatorKind.UI_QUERY,
        }:
            return self._ui_candidates(locator, observation)
        if locator.kind is LocatorKind.OCR_TEXT:
            return self._ocr_candidates(locator, observation)
        if locator.kind is LocatorKind.IMAGE:
            return self._image_candidates(locator, observation)
        if locator.kind is LocatorKind.ANCHOR_OFFSET:
            return self._anchor_candidates(locator, observation)
        if locator.kind is LocatorKind.COORDINATE:
            point = _point_option(locator.options)
            return [_Candidate(point, None, 1.0, "配置坐标", {})] if point else []
        return []

    def _activity_candidates(self, locator: LocatorSpec, observation: Observation) -> list[_Candidate]:
        activity = observation.activity
        if locator.options.get("package_name") not in (None, activity.package_name):
            return []
        if not _text_matches(activity.activity_name, locator.query, locator.options):
            return []
        return [
            _Candidate(
                Point(0.5, 0.5),
                None,
                1.0,
                activity.activity_name,
                {"package_name": activity.package_name},
            )
        ]

    def _ui_candidates(self, locator: LocatorSpec, observation: Observation) -> list[_Candidate]:
        nodes_by_id = {node.node_id: node for node in observation.ui_nodes}
        result: list[_Candidate] = []
        for node in observation.ui_nodes:
            if node.bounds is None or not _matches_primary(locator, node):
                continue
            confidence = _node_confidence(locator, node, nodes_by_id)
            if confidence is None:
                continue
            evidence = node.text or node.description or node.resource_id or node.class_name or node.node_id
            result.append(
                _Candidate(
                    node.bounds.center,
                    node.bounds,
                    confidence,
                    evidence,
                    {"node_id": node.node_id},
                )
            )
        return result

    def _ocr_candidates(self, locator: LocatorSpec, observation: Observation) -> list[_Candidate]:
        items = observation.ocr_texts
        if not items and observation.screenshot is not None and self._ocr is not None:
            key = (observation.observation_id, locator.region)
            if key not in self._ocr_cache:
                self._ocr_cache[key] = self._ocr.recognize(observation.screenshot, locator.region)
            items = self._ocr_cache[key]
        return [
            _Candidate(item.bounds.center, item.bounds, item.confidence, item.text, {"engine": item.engine})
            for item in items
            if _text_matches(item.text, locator.query, locator.options)
            and _inside_region(item.bounds.center, locator.region)
        ]

    def _image_candidates(self, locator: LocatorSpec, observation: Observation) -> list[_Candidate]:
        if not locator.query:
            return []
        items = tuple(item for item in observation.image_matches if item.template_id == locator.query)
        if not items and observation.screenshot is not None and self._images is not None:
            key = (observation.observation_id, locator.query, locator.region)
            if key not in self._image_cache:
                self._image_cache[key] = self._images.match(
                    observation.screenshot,
                    locator.query,
                    locator.region,
                )
            items = self._image_cache[key]
        return [
            _Candidate(
                item.bounds.center,
                item.bounds,
                item.confidence,
                item.template_id,
                {"engine": item.engine},
            )
            for item in items
            if _inside_region(item.bounds.center, locator.region)
        ]

    def _anchor_candidates(self, locator: LocatorSpec, observation: Observation) -> list[_Candidate]:
        raw_kind = locator.options.get("anchor_kind", LocatorKind.UI_TEXT.value)
        anchor_kind = raw_kind if isinstance(raw_kind, LocatorKind) else LocatorKind(str(raw_kind))
        anchor = LocatorSpec(
            strategy_id=f"{locator.strategy_id}:anchor",
            kind=anchor_kind,
            query=locator.query,
            region=locator.region,
            min_confidence=locator.min_confidence,
            options=locator.options.get("anchor_options", {}),
        )
        candidates = self._resolve_locator(anchor, observation)
        offset_x = float(locator.options.get("offset_x", 0.0))
        offset_y = float(locator.options.get("offset_y", 0.0))
        return [
            _Candidate(
                Point(
                    min(1.0, max(0.0, item.point.x + offset_x)),
                    min(1.0, max(0.0, item.point.y + offset_y)),
                ),
                None,
                item.confidence,
                f"锚点偏移: {item.evidence}",
                item.metadata,
            )
            for item in candidates
        ]

    def _select(self, candidates: Sequence[_Candidate], locator: LocatorSpec) -> _Candidate:
        if locator.options.get("pick") == "random" and len(candidates) > 1:
            return self._random.choice(candidates)
        return max(candidates, key=lambda item: item.confidence)


def _matches_primary(locator: LocatorSpec, node: UiNode) -> bool:
    query = locator.query or ""
    if locator.kind is LocatorKind.UI_ID:
        return node.resource_id == query or node.attributes.get("name") == query
    if locator.kind is LocatorKind.UI_TEXT:
        return node.text == query
    if locator.kind is LocatorKind.UI_DESC:
        return node.description == query
    if locator.kind is LocatorKind.UI_REGEX:
        try:
            pattern = re.compile(query)
        except re.error:
            return False
        return any(pattern.search(value or "") for value in (node.text, node.description, node.resource_id))
    if locator.kind is LocatorKind.UI_QUERY and query:
        return query in {node.class_name, node.resource_id, node.text, node.description}
    return locator.kind is LocatorKind.UI_QUERY


def _node_confidence(
    locator: LocatorSpec,
    node: UiNode,
    nodes_by_id: Mapping[str, UiNode],
) -> float | None:
    options = locator.options
    if options.get("visible", True) and node.visible is False:
        return None
    if options.get("enabled", True) and node.enabled is False:
        return None
    for attribute, expected in (
        ("class_name", options.get("class_name")),
        ("resource_id", options.get("resource_id")),
        ("selected", options.get("selected")),
        ("clickable", options.get("clickable")),
    ):
        if expected is not None and getattr(node, attribute) != expected:
            return None
    if not _text_matches(node.text or "", options.get("contains_text"), {"mode": "contains"}):
        return None
    if not _text_matches(node.description or "", options.get("contains_desc"), {"mode": "contains"}):
        return None
    if not _inside_region(node.bounds.center, locator.region):
        return None

    confidence = 1.0
    expected_position = _pair(options.get("position"))
    if expected_position is not None:
        tolerance = float(options.get("position_tolerance", 0.08))
        distance = math.dist((node.bounds.center.x, node.bounds.center.y), expected_position)
        if distance > tolerance:
            return None
        confidence *= max(0.5, 1.0 - distance / max(tolerance, 0.001) * 0.35)
    expected_size = _pair(options.get("size"))
    if expected_size is not None:
        actual_size = (node.bounds.right - node.bounds.left, node.bounds.bottom - node.bounds.top)
        tolerance = float(options.get("size_tolerance", 0.08))
        distance = math.dist(actual_size, expected_size)
        if distance > tolerance:
            return None
        confidence *= max(0.5, 1.0 - distance / max(tolerance, 0.001) * 0.35)
    parent = nodes_by_id.get(node.parent_id or "")
    if options.get("parent_class") and (parent is None or parent.class_name != options["parent_class"]):
        return None
    if options.get("parent_resource_id") and (
        parent is None or parent.resource_id != options["parent_resource_id"]
    ):
        return None
    if options.get("ancestor_resource_id") and not _has_ancestor(
        node,
        nodes_by_id,
        "resource_id",
        options["ancestor_resource_id"],
    ):
        return None
    if options.get("ancestor_class") and not _has_ancestor(
        node,
        nodes_by_id,
        "class_name",
        options["ancestor_class"],
    ):
        return None
    return confidence


def _has_ancestor(
    node: UiNode,
    nodes_by_id: Mapping[str, UiNode],
    attribute: str,
    expected: Any,
) -> bool:
    parent_id = node.parent_id
    while parent_id:
        parent = nodes_by_id.get(parent_id)
        if parent is None:
            return False
        if getattr(parent, attribute) == expected:
            return True
        parent_id = parent.parent_id
    return False


def _text_matches(value: str, query: Any, options: Mapping[str, Any]) -> bool:
    if query in (None, ""):
        return True
    mode = options.get("mode", "contains")
    if mode == "exact":
        return value == str(query)
    if mode == "regex":
        try:
            return re.search(str(query), value) is not None
        except re.error:
            return False
    return str(query) in value


def _inside_region(point: Point, region: Rect | None) -> bool:
    return region is None or (
        region.left <= point.x <= region.right and region.top <= point.y <= region.bottom
    )


def _pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _point_option(options: Mapping[str, Any]) -> Point | None:
    pair = _pair(options.get("point"))
    if pair is None:
        try:
            pair = float(options["x"]), float(options["y"])
        except (KeyError, TypeError, ValueError):
            return None
    return Point(*pair)
