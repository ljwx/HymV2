from __future__ import annotations

from typing import Protocol

from hym.apps.app_specs.douyin import create_plugin as create_douyin_plugin
from hym.apps.app_specs.kuaishou import create_plugin as create_kuaishou_plugin
from hym.apps.app_specs.qutoutiao import create_plugin as create_qutoutiao_plugin
from hym.apps.app_specs.ximalaya import create_plugin as create_ximalaya_plugin
from hym.apps.specs import iter_target_specs
from hym.core.models import AppIdentity, WorkflowResult
from hym.runtime.context import AppContext
from hym.runtime.workflow import WorkflowDefinition


class AppPluginSpec(Protocol):
    identity: AppIdentity
    display_name: str


class AppPlugin(Protocol):
    """运行器只依赖这一小组能力，插件内部流程可以完全不同。"""

    spec: AppPluginSpec

    @property
    def app_id(self) -> str: ...

    def build_workflow(self, context: AppContext) -> WorkflowDefinition: ...

    def run(self, context: AppContext) -> WorkflowResult: ...


class AppRegistry:
    """集中注册插件，新增 App 不需要修改运行器。"""

    def __init__(self) -> None:
        self._plugins: dict[str, AppPlugin] = {}
        self._target_owners: dict[str, str] = {}

    def register(self, plugin: AppPlugin) -> None:
        app_id = plugin.app_id
        if app_id in self._plugins:
            raise ValueError(f"应用插件重复注册: {app_id}")
        for target in iter_target_specs(plugin.spec):
            owner = self._target_owners.get(target.target_id)
            if owner is not None and owner != app_id:
                raise ValueError(
                    f"定位目标 ID 跨应用重复: {target.target_id}（{owner} / {app_id}）"
                )
        self._plugins[app_id] = plugin
        for target in iter_target_specs(plugin.spec):
            self._target_owners[target.target_id] = app_id

    def get(self, app_id: str) -> AppPlugin | None:
        return self._plugins.get(app_id)

    def app_ids(self) -> tuple[str, ...]:
        return tuple(self._plugins)


def create_default_registry() -> AppRegistry:
    registry = AppRegistry()
    plugin_factories = (
        create_kuaishou_plugin,
        create_douyin_plugin,
        create_qutoutiao_plugin,
        create_ximalaya_plugin,
    )
    for plugin_factory in plugin_factories:
        registry.register(plugin_factory())
    return registry
