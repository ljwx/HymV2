from __future__ import annotations

from hym.core.ports import RandomPort


def bounded_normal(
    random_source: RandomPort,
    minimum: float,
    maximum: float,
    *,
    center: float | None = None,
    stddev: float | None = None,
) -> float:
    """生成有界正态随机数，少量极端值会被截断到配置范围。"""

    if minimum > maximum:
        raise ValueError("正态随机范围无效")
    if minimum == maximum:
        return minimum
    middle = (minimum + maximum) / 2 if center is None else center
    if not minimum <= middle <= maximum:
        raise ValueError("正态随机中心必须位于配置范围内")
    deviation = (maximum - minimum) / 6 if stddev is None else stddev
    if deviation <= 0:
        raise ValueError("正态随机标准差必须大于零")

    sampled = random_source.normalvariate(middle, deviation)
    return min(maximum, max(minimum, sampled))


def bounded_normal_int(
    random_source: RandomPort,
    minimum: int,
    maximum: int,
    *,
    center: float | None = None,
    stddev: float | None = None,
) -> int:
    """生成有界正态整数，适用于内容条数和任务次数。"""

    sampled = bounded_normal(
        random_source,
        float(minimum),
        float(maximum),
        center=center,
        stddev=stddev,
    )
    return min(maximum, max(minimum, round(sampled)))
