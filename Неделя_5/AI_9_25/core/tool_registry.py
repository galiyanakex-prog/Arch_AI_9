"""core/tool_registry.py — каталог инструментов всех источников (День 16).

Реестр **каталогизирует**, но не контролирует: не проверяет бизнес-правила и
не вызывает StateMachine (канон Рекомендации_MCP_d16.txt). Обновление — только
полным атомарным snapshot: один запрос модели никогда не видит «половину
старого и половину нового» каталога.
"""

from __future__ import annotations

from core.tools import ToolCatalogSnapshot, ToolDescriptor, ToolProvider


def _schema_is_valid(schema: object) -> bool:
    """JSON Schema-примитивы: dict с type=object; properties/required опциональны."""
    if not isinstance(schema, dict):
        return False
    if schema.get("type") != "object":
        return False
    props = schema.get("properties")
    if props is not None and not isinstance(props, dict):
        return False
    req = schema.get("required")
    if req is not None and not (isinstance(req, list) and all(isinstance(i, str) for i in req)):
        return False
    return True


class ToolRegistry:
    """Каталог инструментов всех источников (local + mcp + …)."""

    def __init__(self) -> None:
        self._providers: dict[str, ToolProvider] = {}
        self._version: int = 0
        self._current_snapshot: ToolCatalogSnapshot = ToolCatalogSnapshot(
            version=0, tools=()
        )

    # -- провайдеры ---------------------------------------------------------

    def add_provider(self, provider: ToolProvider) -> None:
        pid = provider.provider_id()
        if pid in self._providers:
            print(f"[Реестр] провайдер «{pid}» заменён")
        self._providers[pid] = provider

    def unregister_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    # -- чтение -------------------------------------------------------------

    def get(self, name: str) -> ToolDescriptor:
        """Дескриптор по квалифицированному имени; неизвестное — понятная ошибка."""
        for tool in self._current_snapshot.tools:
            if tool.name == name:
                return tool
        known = ", ".join(t.name for t in self._current_snapshot.tools) or "—"
        raise KeyError(
            f"Инструмент «{name}» не найден в каталоге. Доступны: {known}"
        )

    def available_for(self, context: object = None) -> list[ToolDescriptor]:
        """Тулы, доступные в данном контексте (задел: фильтры policy — день 17+)."""
        return list(self._current_snapshot.tools)

    def snapshot(self) -> ToolCatalogSnapshot:
        """Текущий snapshot без пересборки (атомарное чтение)."""
        return self._current_snapshot

    # -- обновление (атомарное) ----------------------------------------------

    def refresh(self) -> ToolCatalogSnapshot:
        """discover() у всех провайдеров → валидация → коллизии → атомарный swap."""
        collected: list[ToolDescriptor] = []
        for pid, provider in list(self._providers.items()):
            try:
                tools = provider.discover()
            except Exception as exc:  # недоступный провайдер изолирован
                print(f"[Реестр] провайдер «{pid}» недоступен: {exc}")
                continue
            for tool in tools:
                if not _schema_is_valid(tool.input_schema):
                    print(
                        f"[Реестр] тул «{tool.name}» исключён: "
                        "невалидная input_schema (нужен dict с type=object)"
                    )
                    continue
                collected.append(tool)

        # коллизии квалифицированных имён: последний побеждает + лог
        by_name: dict[str, ToolDescriptor] = {}
        for tool in collected:
            if tool.name in by_name:
                print(f"[Реестр] коллизия имени «{tool.name}»: перезапись")
            by_name[tool.name] = tool

        self._version += 1
        new_snapshot = ToolCatalogSnapshot(
            version=self._version, tools=tuple(by_name.values())
        )
        self._current_snapshot = new_snapshot  # атомарный swap
        return new_snapshot
