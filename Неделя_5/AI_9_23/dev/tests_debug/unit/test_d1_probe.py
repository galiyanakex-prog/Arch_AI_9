# -*- coding: utf-8 -*-
"""Юнит-тест D1 (Ревизия 5): порог probe + enabled-политика серверов.

Проверяет детерминированно (без сети):
  * scheduler/pipeline по умолчанию `enabled=False`, но зарегистрированы;
  * env-флаги SCHEDULER_MCP_ENABLED/PIPELINE_MCP_ENABLED включают их;
  * `overall_state()` не изменён (семантика состояний — инвариант).

Формат — модульные функции `test_*` (конвенция dev/tests_debug/unit_runner.py).
"""
import importlib
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def test_scheduler_pipeline_disabled_by_default_but_registered():
    from integrations.mcp.config import DEFAULT_SERVERS
    by_id = {s.server_id: s for s in DEFAULT_SERVERS}
    assert "scheduler" in by_id, "scheduler должен остаться зарегистрированным"
    assert "pipeline" in by_id, "pipeline должен остаться зарегистрированным"
    assert by_id["scheduler"].enabled is False, "scheduler по умолчанию выключен (D1)"
    assert by_id["pipeline"].enabled is False, "pipeline по умолчанию выключен (D1)"
    assert by_id["time"].enabled is True, "time — сервер задания, включён"


def test_env_flags_enable_servers():
    os.environ["SCHEDULER_MCP_ENABLED"] = "1"
    os.environ["PIPELINE_MCP_ENABLED"] = "true"
    try:
        import integrations.mcp.config as cfg
        importlib.reload(cfg)
        by_id = {s.server_id: s for s in cfg.DEFAULT_SERVERS}
        assert by_id["scheduler"].enabled is True
        assert by_id["pipeline"].enabled is True
    finally:
        os.environ.pop("SCHEDULER_MCP_ENABLED", None)
        os.environ.pop("PIPELINE_MCP_ENABLED", None)
        import integrations.mcp.config as cfg
        importlib.reload(cfg)


def test_overall_state_semantics_unchanged():
    from integrations.mcp.gateway import MCPGateway, MCPConnectionState
    from integrations.mcp.config import MCPServerConfig
    gw = MCPGateway([MCPServerConfig(server_id="a", transport="http",
                                     endpoint="x", enabled=True)])
    gw._states = {"a": MCPConnectionState.READY, "b": MCPConnectionState.FAILED}
    assert gw.overall_state() == MCPConnectionState.DEGRADED
    gw._states = {"a": MCPConnectionState.READY}
    assert gw.overall_state() == MCPConnectionState.READY
    gw._states = {"a": MCPConnectionState.FAILED}
    assert gw.overall_state() == MCPConnectionState.FAILED