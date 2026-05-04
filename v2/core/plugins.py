"""Plugin registry stub for future modular handlers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


class PluginRegistry:
    """Collects named plugins; real bot wiring comes in later phases."""

    def __init__(self) -> None:
        self._plugins: Dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        if name in self._plugins:
            raise ValueError(f"plugin already registered: {name}")
        self._plugins[name] = plugin

    def get(self, name: str) -> Any:
        return self._plugins[name]

    def names(self) -> List[str]:
        return sorted(self._plugins.keys())


Handler = Callable[..., Any]
