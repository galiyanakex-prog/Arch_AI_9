#!/bin/bash
# check_acceptance.sh — гейт приёмки (§7.1 START-PROMT.md).
# Идемпотентен: использует временный каталог dev/tests_debug/.tmp/acc_$$ и НЕ трогает users/ дня.
# Запуск: cd "$KOD" && API_KEY=test-key bash "$TST/check_acceptance.sh"

set -u
# Скрипт лежит в <день>/dev/tests_debug/ → KOD = два уровня вверх (корень дня).
KOD="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$KOD/.venv/bin/python"   # venv корня AI_9 (после переноса дня в корень)
TST="$KOD/dev/tests_debug"
TMP="$TST/.tmp/acc_$$"
mkdir -p "$TMP"
PASS=0; FAIL=0; TOTAL=0

check() {  # check <описание> <команда...>
  TOTAL=$((TOTAL+1))
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  [$TOTAL] ✅ $desc"
    PASS=$((PASS+1))
  else
    echo "  [$TOTAL] ❌ $desc"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Приёмка ==="

# 1. Комплектность и сборка (L1)
check "py_compile всей сборки" "$PY" -m py_compile "$KOD/Kod.py" "$KOD"/core/*.py "$KOD"/memory/*.py "$KOD"/storage/*.py
check "README непустой" test -s "$KOD/README.md"
check "run.sh исполняемый" test -x "$KOD/run.sh"
check "run.desktop непустой" test -s "$KOD/run.desktop"

# 2..13, 17: юнит-тесты (L2)
check "юнит-тесты памяти/хранилища/промта/LLM/стейта/агента" env -u API_KEY "$PY" "$TST/unit_runner.py"

# 14: демонстрации (manual) — закрываются прогоном scenario (L4)
check "сценарии задания (L4)" env API_KEY=test-key "$PY" "$TST/scenario.py"

# 15: текстовое описание модели памяти
check "README содержит раздел модели памяти" grep -q "Модель памяти" "$KOD/README.md"

# 16: токен-учёт и CSV (наличие флага и журнала)
check "CSV-журнал токенов создаётся (local smoke)" bash -c "cd '$KOD' && printf 'a\nX\nu\nu\nu\nHi\n/exit\n' | API_KEY=test-key '$PY' Kod.py --mock --memory-dir '$TMP/users' --log '$TMP/log.md' --token-log '$TMP/tokens.csv' >/dev/null 2>&1 && test -f '$TMP/tokens.csv'"

# 19: Проверка.md только в dev/
check "в корне дня нет Проверка.md" bash -c "test ! -e '$KOD/Проверка.md'"

# 20 (День 15): task_state.json создаётся и переживает перезапуск (пауза → resume).
# Прогон 1: /plan → /approve → /step → /pause → /exit (снимок на диске, stage=paused).
# Прогон 2 (новый процесс, тот же memory-dir): /resume → /run → done.
check "task_state.json переживает перезапуск (пауза→resume→done)" bash -c "
  set -e
  D='$TMP/fsm'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/approve\n/step\n/pause\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"paused\"' \"\$SNAP\"
  printf '/resume
/run
/exit
' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --user u --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  grep -q '\"stage\": \"done\"' \"\$SNAP\"
"

# 21 (День 14): инварианты хранятся отдельно от диалога и переживают перезапуск.
# Прогон 1: добавить инвариант → invariants.json на диске (отдельный от session.json).
# Прогон 2 (новый процесс, тот же memory-dir): /invariants видит правило.
check "инварианты хранятся отдельно и переживают перезапуск" bash -c "
  set -e
  D='$TMP/inv'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/invariant add framework.django architecture Django\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  INV=\$(find \"\$MD\" -name invariants.json | head -n1)
  test -n \"\$INV\"
  grep -q 'framework.django' \"\$INV\"
  printf '/invariants\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --user u --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" 2>/dev/null | grep -q 'framework.django'
"

# 22 (День 14): конфликт запроса и инварианта → отказ (действие не исполняется).
check "конфликт запроса и инварианта → отказ" bash -c "
  '$PY' - <<'PYEOF'
import os, sys, tempfile
sys.path.insert(0, '$KOD')
from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor
from core.invariants import Invariant
tmp = tempfile.mkdtemp(prefix='acc_inv_', dir='$TMP')
root = os.path.join(tmp, 'users')
store = Store(root, profile_repo=ProfileRepository(os.path.join(root, 'p.db')))
a = Agent(MockClient(), MemoryManager(default_layers(store)), PromptBuilder('r'), store,
          user_id='u', executor=StubExecutor())
a.initialize_user('u', 'И', {'style':'a','constraints':'b','context':'c'})
a.add_invariant(Invariant(id='framework.django', category='architecture', description='Django'))
before = a.tool_calls
res = a.propose_and_check('перепиши API на FastAPI')
assert res['allowed'] is False and a.tool_calls == before
assert 'framework.django' in res['message']
print('ok')
PYEOF
"

# 23 (День 15): недопустимый переход блокируется кодом и логируется.
# /plan → /goto implementation → ОТКАЗАНО; stage не изменилась (planning);
# в task_state.json есть transition_log с allowed=false.
check "недопустимый переход блокируется кодом и логируется" bash -c "
  set -e
  D='$TMP/goto'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/goto implementation\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" 2>/dev/null | grep -q 'ОТКАЗАНО'
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"planning\"' \"\$SNAP\"
  grep -q '\"allowed\": false' \"\$SNAP\"
  grep -qi 'нельзя делать реализацию до утверждённого плана' \"\$SNAP\"
"

# 24 (День 15): флоу утверждения плана (/plan → /approve → /run → done).
check "флоу утверждения плана (/approve)" bash -c "
  set -e
  D='$TMP/approve'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/approve\n/run\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" 2>/dev/null | grep -q 'утверждён'
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"done\"' \"\$SNAP\"
  grep -q '\"to\": \"plan_approved\"' \"\$SNAP\"
"

# 25 (День 15): пауза → перезапуск процесса → resume → done (шаг не повторён).
# Прогон 1: /plan → /approve → /step → /pause → /exit (1 результат, paused).
# Прогон 2 (новый процесс, тот же memory-dir): /resume → /run → done (3 результата).
check "пауза → перезапуск → resume (шаг не повторён)" bash -c "
  set -e
  D='$TMP/pause15'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/approve\n/step\n/pause\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"paused\"' \"\$SNAP\"
  test \"\$(grep -c 'Результат шага' \"\$SNAP\")\" = \"1\"
  printf '/resume\n/run\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --user u --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  grep -q '\"stage\": \"done\"' \"\$SNAP\"
  test \"\$(grep -c 'Результат шага' \"\$SNAP\")\" = \"3\"
"

# 26–28 (День 16): --mcp-probe на fake-транспорте (без сети и stdio-подпроцессов).
# Обёртка получает корень дня через ACC_BASE (надёжнее подсчёта dirname) и
# подменяет load_servers_config/MCPGatewaySync ДО вызова run_mcp_probe().
# 26: exit 0 + READY + 3 тула; 27: имена mcp.demo.*;
# 28: description + input_schema каждого тула в выводе.
check "--mcp-probe (fake) → READY, 3 тула, exit 0" bash -c "
  set -e
  D='$TMP/probe'; mkdir -p \"\$D\"
  cat > \"\$D/wrapper.py\" <<'WEOF'
# -*- coding: utf-8 -*-
import os, sys
BASE = os.environ['ACC_BASE']
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, 'Kod.py')]
import Kod
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
import integrations.mcp.config as mcp_config
import integrations.mcp.gateway as mcp_gateway_mod
FAKE_TOOLS = [
    {'name': 'get_time', 'description': 'Текущее время',
     'inputSchema': {'type': 'object', 'properties': {}, 'required': []}},
    {'name': 'echo', 'description': 'Повтор текста',
     'inputSchema': {'type': 'object',
                     'properties': {'text': {'type': 'string'}},
                     'required': ['text']}},
    {'name': 'weather_stub', 'description': 'Погода (заглушка)',
     'inputSchema': {'type': 'object',
                     'properties': {'location': {'type': 'string'},
                                    'units': {'type': 'string'}},
                     'required': ['location']}},
]
def fake_servers():
    return [MCPServerConfig(server_id='demo', transport='stdio',
                            command='python', enabled=True, trust_level='low')]
class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {'demo': FakeMCPTransport(FAKE_TOOLS, server_id='demo')})
    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync
sys.exit(Kod.run_mcp_probe())
WEOF
  ACC_BASE='$KOD' '$PY' \"\$D/wrapper.py\" >\"\$D/out.txt\" 2>&1
  grep -q 'Соединение установлено (READY' \"\$D/out.txt\"
  grep -q 'Всего инструментов: 3' \"\$D/out.txt\"
  grep -q 'Соединение закрыто (DISCONNECTED)' \"\$D/out.txt\"
"

check "имена mcp.demo.* в выводе probe" bash -c "
  set -e
  D='$TMP/probe2'; mkdir -p \"\$D\"
  cat > \"\$D/wrapper.py\" <<'WEOF'
# -*- coding: utf-8 -*-
import os, sys
BASE = os.environ['ACC_BASE']
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, 'Kod.py')]
import Kod
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
import integrations.mcp.config as mcp_config
import integrations.mcp.gateway as mcp_gateway_mod
FAKE_TOOLS = [
    {'name': 'get_time', 'description': 'Текущее время',
     'inputSchema': {'type': 'object', 'properties': {}, 'required': []}},
    {'name': 'echo', 'description': 'Повтор текста',
     'inputSchema': {'type': 'object',
                     'properties': {'text': {'type': 'string'}},
                     'required': ['text']}},
    {'name': 'weather_stub', 'description': 'Погода (заглушка)',
     'inputSchema': {'type': 'object',
                     'properties': {'location': {'type': 'string'},
                                    'units': {'type': 'string'}},
                     'required': ['location']}},
]
def fake_servers():
    return [MCPServerConfig(server_id='demo', transport='stdio',
                            command='python', enabled=True, trust_level='low')]
class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {'demo': FakeMCPTransport(FAKE_TOOLS, server_id='demo')})
    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync
sys.exit(Kod.run_mcp_probe())
WEOF
  ACC_BASE='$KOD' '$PY' \"\$D/wrapper.py\" >\"\$D/out.txt\" 2>&1
  grep -q 'mcp.demo.get_time' \"\$D/out.txt\"
  grep -q 'mcp.demo.echo' \"\$D/out.txt\"
  grep -q 'mcp.demo.weather_stub' \"\$D/out.txt\"
"

check "имя + description + input_schema тула в probe" bash -c "
  set -e
  D='$TMP/probe3'; mkdir -p \"\$D\"
  cat > \"\$D/wrapper.py\" <<'WEOF'
# -*- coding: utf-8 -*-
import os, sys
BASE = os.environ['ACC_BASE']
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, 'Kod.py')]
import Kod
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
import integrations.mcp.config as mcp_config
import integrations.mcp.gateway as mcp_gateway_mod
FAKE_TOOLS = [
    {'name': 'get_time', 'description': 'Текущее время',
     'inputSchema': {'type': 'object', 'properties': {}, 'required': []}},
    {'name': 'echo', 'description': 'Повтор текста',
     'inputSchema': {'type': 'object',
                     'properties': {'text': {'type': 'string'}},
                     'required': ['text']}},
    {'name': 'weather_stub', 'description': 'Погода (заглушка)',
     'inputSchema': {'type': 'object',
                     'properties': {'location': {'type': 'string'},
                                    'units': {'type': 'string'}},
                     'required': ['location']}},
]
def fake_servers():
    return [MCPServerConfig(server_id='demo', transport='stdio',
                            command='python', enabled=True, trust_level='low')]
class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {'demo': FakeMCPTransport(FAKE_TOOLS, server_id='demo')})
    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync
sys.exit(Kod.run_mcp_probe())
WEOF
  ACC_BASE='$KOD' '$PY' \"\$D/wrapper.py\" >\"\$D/out.txt\" 2>&1
  grep -q 'description: Текущее время' \"\$D/out.txt\"
  grep -q 'description: Повтор текста' \"\$D/out.txt\"
  grep -q 'description: Погода (заглушка)' \"\$D/out.txt\"
  grep -q '\"required\": \[\"text\"\]' \"\$D/out.txt\"
  grep -q '\"required\": \[\"location\"\]' \"\$D/out.txt\"
"

# 29 (Ревизия 2): HTTP-транспорт выбирается по конфигу; фикс чтения схемы (input_schema).
check "HTTP-транспорт и фикс input_schema" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import make_transport, HttpMCPTransport, StdioMCPTransport, _tool_schema
h = MCPServerConfig(server_id='w', transport='http', endpoint='https://x/mcp/')
s = MCPServerConfig(server_id='d', transport='stdio', command=('python', '-m', 'x'))
assert isinstance(make_transport(h), HttpMCPTransport)
assert isinstance(make_transport(s), StdioMCPTransport)
class T: name='t'; description='d'; input_schema={'type':'object','required':['q']}
assert _tool_schema(T())['required'] == ['q']
print('ok')
PYEOF
"

# 30 (Ревизия 2): tools/call на fake-транспорте → результат; ToolPolicy/ToolExecutor + аудит.
check "tools/call + policy + аудит (fake)" bash -c "
  '$PY' - <<'PYEOF'
import sys, tempfile, os, asyncio
sys.path.insert(0, '$KOD')
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
from integrations.mcp.gateway import MCPGateway
from integrations.mcp.provider import MCPToolProvider
from core.tool_registry import ToolRegistry
from core.tool_policy import ToolPolicy
from core.tool_executor import ToolExecutor
from core.tools import ToolCallRequest, ToolExecutionState
from storage.store import Store
TOOLS=[{'name':'echo','description':'e','inputSchema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}]
gw=MCPGateway([MCPServerConfig(server_id='demo',transport='stdio',command=('python',),enabled=True)],
              {'demo':FakeMCPTransport(TOOLS,server_id='demo',tool_results={'echo':'hi'})})
asyncio.run(gw.start())
reg=ToolRegistry(); reg.add_provider(MCPToolProvider(gw)); reg.refresh()
tmp=tempfile.mkdtemp(prefix='acc_tooluse_',dir='$TMP')
store=Store(os.path.join(tmp,'users'))
ex=ToolExecutor(reg,ToolPolicy(),gw,store=store)
r=ex.execute(ToolCallRequest('mcp.demo.echo',{'text':'hi'}),user_id='u',task='T',task_stage='implementation')
assert r.status==ToolExecutionState.SUCCEEDED.value and r.summary=='hi', r
assert store.load_tool_audit('u','T')[0]['tool']=='mcp.demo.echo'
d=ex.execute(ToolCallRequest('mcp.demo.echo',{}),user_id='u',task='T',task_stage='implementation')
assert d.status==ToolExecutionState.DENIED.value
print('ok')
PYEOF
"

# 31 (Ревизия 2): блок [tools] в промте + LLM tool-use цикл (MockClient) → вызов тула.
check "LLM tool-use: блок [tools] + цикл (mock)" bash -c "
  '$PY' - <<'PYEOF'
import sys, tempfile, os, asyncio
sys.path.insert(0, '$KOD')
from core.prompt_builder import PromptBuilder, BLOCK_ORDER
from core.tools import ToolDescriptor
from core.agent import PromptContext
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
from integrations.mcp.gateway import MCPGateway
from integrations.mcp.provider import MCPToolProvider
from core.tool_registry import ToolRegistry
from core.tool_policy import ToolPolicy
from core.tool_executor import ToolExecutor
from core.invariants import RuleBasedChecker
from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.agent import Agent, StubExecutor
tool=ToolDescriptor(name='mcp.weather.search_locations',description='city',input_schema={'type':'object'},
                    source='mcp',provider='weather',original_name='search_locations')
pb=PromptBuilder('ROLE'); ctx=PromptContext('найди Москва',{},tools=[tool])
assert any('[tools]' in m['content'] for m in pb.build(ctx,{'tools'}))
assert BLOCK_ORDER.index('tools')==BLOCK_ORDER.index('invariants')+1
tmp=tempfile.mkdtemp(prefix='acc_tooluse2_',dir='$TMP')
store=Store(os.path.join(tmp,'users'),profile_repo=ProfileRepository(os.path.join(tmp,'p.db')))
TOOLS=[{'name':'search_locations','description':'c','inputSchema':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}]
gw=MCPGateway([MCPServerConfig(server_id='weather',transport='http',endpoint='x',enabled=True)],
              {'weather':FakeMCPTransport(TOOLS,server_id='weather',tool_results={'search_locations':'{\"results\":[{\"name\":\"Moscow\"}]}'})})
asyncio.run(gw.start())
reg=ToolRegistry(); reg.add_provider(MCPToolProvider(gw)); reg.refresh()
a=Agent(MockClient(),MemoryManager(default_layers(store)),PromptBuilder('ROLE'),store,user_id='u',executor=StubExecutor())
a.initialize_user('u','И',{'style':'a','constraints':'b','context':'c'})
a.mcp_gateway=gw; a.tool_registry=reg
a.tool_executor=ToolExecutor(reg,ToolPolicy(),gw,store=store,checker=RuleBasedChecker())
a.deliver.add('tools')
ans=a.respond('найди город Москва')
assert 'Moscow' in ans, ans
assert store.load_tool_audit('u',a.task)[0]['tool']=='mcp.weather.search_locations'
print('ok')
PYEOF
"

# 32 (День 20, D3): мультисерверный длинный флоу — Grep по детерминированному
# сценарию (несколько серверов, порядок, без лишних) уже включён в L4 (check 6).
check "мультисерверный флоу D3 (scenario L4)" grep -q "D3: мультисерверный длинный флоу" "$TST/scenario.py"

# 33 (День 20, D4): ранжирование инструментов (rank_tools) — RU→EN-эвристика.
check "ранжирование инструментов D4 (rank_tools)" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from core.tool_routing import rank_tools
from core.tools import ToolDescriptor
tools=[ToolDescriptor(name='mcp.time.get_time',description='Текущее время',input_schema={'type':'object'},source='mcp',provider='time',original_name='get_time'),
ToolDescriptor(name='mcp.pipeline.search',description='Получить данные',input_schema={'type':'object'},source='mcp',provider='pipeline',original_name='search'),
ToolDescriptor(name='mcp.scheduler.schedule_reminder',description='Напоминание',input_schema={'type':'object'},source='mcp',provider='scheduler',original_name='schedule_reminder')]
assert rank_tools('который час',tools)[0].name=='mcp.time.get_time'
assert rank_tools('собери данные',tools)[0].name=='mcp.pipeline.search'
assert rank_tools('напомни о сводке',tools)[0].name=='mcp.scheduler.schedule_reminder'
assert rank_tools('абвгд непонятное',tools)==[]
print('ok')
PYEOF
"

# 34 (День 20, D6): пакет мелких исправлений — connect по id, полный text,
# терминальные стадии read-only, валидный tool_calls.
check "пакет исправлений D6 (connect/text/terminal/tool_calls)" bash -c "
  '$PY' - <<'PYEOF'
import sys, asyncio
sys.path.insert(0, '$KOD')
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.gateway import MCPGateway
from integrations.mcp.transport import FakeMCPTransport
from core.tools import ToolDescriptor, ToolCallRequest, ToolExecutionResult
from core.tool_policy import ToolPolicy
tools=[{'name':'get_time','description':'t','inputSchema':{'type':'object','properties':{},'required':[]}}]
servers=[MCPServerConfig(server_id='time',transport='stdio',command='python',enabled=True),
         MCPServerConfig(server_id='scheduler',transport='stdio',command='python',enabled=True)]
tr={'time':FakeMCPTransport(tools,server_id='time'),'scheduler':FakeMCPTransport(tools,server_id='scheduler')}
gw=MCPGateway(servers,tr); asyncio.run(gw.start(only_server='time'))
st=gw.status()['servers']
assert st['time']=='ready' and st['scheduler']=='disconnected', st
long='x'*1200
r=ToolExecutionResult(execution_id='1',tool='t',status='succeeded',summary=long[:500],text=long)
assert len(r.summary)==500 and len(r.text)==1200
pol=ToolPolicy()
ro=ToolDescriptor(name='mcp.time.get_time',description='t',input_schema={'type':'object'},source='mcp',provider='time',original_name='get_time')
mut=ToolDescriptor(name='mcp.pipeline.saveToFile',description='s',input_schema={'type':'object'},source='mcp',provider='pipeline',original_name='saveToFile')
assert pol.check(ro,ToolCallRequest('mcp.time.get_time',{}),task_stage='done').allowed
assert not pol.check(mut,ToolCallRequest('mcp.pipeline.saveToFile',{'name':'x','content':'y'}),task_stage='done').allowed
print('ok')
PYEOF
"

# 35 (День 20, D7): авторизация транспорта — заголовки из env + серверный 401.
check "авторизация транспорта D7 (Bearer/401)" bash -c "
  '$PY' - <<'PYEOF'
import sys, os, asyncio
sys.path.insert(0, '$KOD')
from integrations.mcp.transport import HttpMCPTransport
from integrations.mcp.config import _parse_server
from integrations.mcp.auth import auth_middleware
os.environ['TEST_MCP_TOKEN']='s3cr3t'
tr=HttpMCPTransport('time','http://x/mcp',token_env='TEST_MCP_TOKEN',headers={'X-Trace':'1'})
h=tr._auth_headers()
assert h['Authorization']=='Bearer s3cr3t' and h['X-Trace']=='1', h
os.environ.pop('TEST_MCP_TOKEN',None)
cfg=_parse_server({'server_id':'s','transport':'http','endpoint':'http://x','token_env':'TOK','headers':{'X':'y'}})
assert cfg.token_env=='TOK' and cfg.headers=={'X':'y'}
os.environ['MCP_AUTH_TOKEN']='tok'
async def inner(scope,receive,send):
    await send({'type':'http.response.start','status':200,'headers':[]})
    await send({'type':'http.response.body','body':b'ok'})
app=auth_middleware(inner)
def run(headers):
    scope={'type':'http','method':'POST','path':'/mcp','headers':[(k.lower().encode(),v.encode()) for k,v in headers.items()]}
    sent=[]
    async def recv(): return {'type':'http.request','body':b'','more_body':False}
    async def send(m): sent.append(m)
    asyncio.run(app(scope,recv,send))
    return next(m['status'] for m in sent if m['type']=='http.response.start')
assert run({})==401 and run({'Authorization':'Bearer wrong'})==401 and run({'Authorization':'Bearer tok'})==200
os.environ.pop('MCP_AUTH_TOKEN',None)
print('ok')
PYEOF
"

# --- Ревизия 6: RAG-модуль (этап 11, +8 проверок: 26..33) -------------------------

# 26: импорт rag (пакет собирается, публичный API доступен).
check "RAG: импорт пакета rag" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
import rag
from rag import RagService, RagConfig, Hit, Chunk
assert RagService and RagConfig and Hit and Chunk
print('ok')
PYEOF
"

# 27: индекс строится (hashing-эмбеддер, без Ollama) и переживает save/load.
check "RAG: индекс строится и переживает save/load" bash -c "
  '$PY' - <<'PYEOF'
import sys, os, tempfile
sys.path.insert(0, '$KOD')
from rag.config import RagConfig
from rag.chunking import chunk_document
from rag.embedding import HashingEmbedder
from rag.index import RagIndex
cfg = RagConfig.default()
doc = {'doc_id': 'd1', 'source': 'a.md', 'title': 'A', 'text': 'BM25 ранжирует документы. ' * 40,
       'sha1': 'x', 'mtime': 1.0, 'content_type': 'text'}
chunks = chunk_document(doc, cfg.chunking, 'fixed')
assert chunks, 'нет чанков'
idx = RagIndex(cfg).build(chunks, HashingEmbedder(dim=64))
assert len(idx.chunks) == len(chunks)
with tempfile.TemporaryDirectory() as d:
    idx.save(d)
    again = RagIndex.load(d, cfg)
    assert len(again.chunks) == len(chunks), 'индекс не пережил перезапуск'
print('ok')
PYEOF
"

# 28: поиск отдаёт ≥1 хит с метаданными (source/section/chunk_id).
check "RAG: поиск отдаёт хит с метаданными" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.config import RagConfig
from rag.chunking import chunk_document
from rag.embedding import HashingEmbedder
from rag.index import RagIndex
from rag.retrieval import Retriever
cfg = RagConfig.default()
doc = {'doc_id': 'd1', 'source': 'core/invariants.py', 'title': 'Инварианты',
       'text': 'Инварианты запрещают менять технологический стек проекта. ' * 30,
       'sha1': 'x', 'mtime': 1.0, 'content_type': 'text'}
chunks = chunk_document(doc, cfg.chunking, 'fixed')
idx = RagIndex(cfg).build(chunks, HashingEmbedder(dim=64))
hits = Retriever(idx, cfg, HashingEmbedder(dim=64)).search('инварианты стек', k=3, mode='bm25')
assert hits, 'нет хитов'
h = hits[0]
assert h.chunk_id and h.source and h.doc_id, 'нет метаданных'
print('ok')
PYEOF
"

# 29: обе стратегии чанкинга дают РАЗНОЕ разбиение.
check "RAG: две стратегии чанкинга дают разное разбиение" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.config import RagConfig
from rag.chunking import chunk_document
cfg = RagConfig.default()
text = ('# Раздел A\n\n' + 'Первый абзац про инварианты. ' * 20 + '\n\n'
        + '# Раздел B\n\n' + 'Второй абзац про бюджет токенов. ' * 20)
doc = {'doc_id': 'd1', 'source': 'a.md', 'title': 'A', 'text': text,
       'sha1': 'x', 'mtime': 1.0, 'content_type': 'text'}
fixed = chunk_document(doc, cfg.chunking, 'fixed')
structural = chunk_document(doc, cfg.chunking, 'structural')
assert fixed and structural, 'пустое разбиение'
assert [c.text for c in fixed] != [c.text for c in structural], 'разбиения совпали'
print('ok')
PYEOF
"

# 30: отчёт сравнения стратегий существует.
check "RAG: отчёт сравнения стратегий существует" test -s "$KOD/dev/logs_reports/stages/rag_chunking_compare.md"

# 31: без --rag промпт НЕ содержит блок [rag] (регрессия байт-в-байт).
check "RAG: без --rag промпт не содержит [rag]" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from core.prompt_builder import PromptBuilder
from core.agent import PromptContext
ctx = PromptContext(query='вопрос', memory_blocks={'profile': 'П', 'invariants': 'И',
                    'long_term': 'Д', 'working': 'Р'}, short_term_messages=[])
msgs = PromptBuilder('Ты ассистент').build(ctx, {'role','profile','invariants','long_term','working','short_term','current'})
joined = '\n'.join(m.get('content','') for m in msgs)
assert '[rag]' not in joined, 'блок [rag] просочился без --rag'
print('ok')
PYEOF
"

# 32: RAG не меняет TaskStage (набор стадий неизменен).
check "RAG: TaskStage не затронут" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from core.state_machine import TaskStage
expected = {'new','planning','plan_approved','implementation','validation','done','paused','failed'}
assert {s.value for s in TaskStage} == expected, {s.value for s in TaskStage}
print('ok')
PYEOF
"

# 33: --rag-eval завершается с hit-rate@5 ≥ 0.80 (живой индекс; пропуск без индекса).
check "RAG: --rag-eval hit-rate@5 ≥ 0.80" bash -c "
  if [ ! -f '$KOD/rag/index/meta.json' ]; then echo 'индекс отсутствует — пропуск'; exit 0; fi
  OUT=\$('$PY' '$KOD/Kod.py' --rag-eval 2>&1)
  echo \"\$OUT\" | grep -q 'hit_rate@k' || { echo 'нет метрики'; exit 1; }
  HR=\$(echo \"\$OUT\" | grep 'hit_rate@k' | head -n1 | sed 's/.*: //')
  awk -v hr=\"\$HR\" 'BEGIN { exit (hr+0 >= 0.80) ? 0 : 1 }'
"

# --- Ревизия 7: RAG-модуль (части 1–4 Задание.txt, +10 проверок: 34..43) ----------

# 34: новые модули Ревизии 7 импортируются (rewrite/sources/citations/verify + типы).
check "RAG7: импорт новых модулей (rewrite/sources/citations/verify)" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.rewrite import rewrite
from rag.sources import build_sources, render_sources
from rag.citations import build_quotes, render_quotes
from rag.verify import verify_answers, render_report
from rag.types import Source, Quote
print('ok')
PYEOF
"

# 35: query rewrite — снятие шумовых оборотов + подтягивание терминов из истории.
check "RAG7: rewrite убирает шум и подтягивает термины из истории" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.rewrite import rewrite
clean = rewrite('пожалуйста, расскажи про бюджет токенов')
assert 'пожалуйста' not in clean.lower(), clean
assert 'бюджет' in clean.lower(), clean
enriched = rewrite('а как это работает', history=['как устроен RAG-модуль проекта'])
assert len(enriched.split()) > len('а как это работает'.split()), enriched
print('ok')
PYEOF
"

# 36: источники (дедуп по chunk_id, сорт по скору) и цитаты из чанков.
check "RAG7: источники (дедуп/сорт) и цитаты из чанков" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.sources import build_sources
from rag.citations import build_quotes
from rag.types import Hit
def hit(cid, score, text='бюджет токенов промпта'):
    return Hit(chunk_id=cid, doc_id=cid.split('#')[0], source='a.py', title='',
               section='S', text=text, score=score)
src = build_sources([hit('d1#0', 0.5), hit('d2#0', 0.9), hit('d1#0', 0.5)])
assert len(src) == 2 and src[0].chunk_id == 'd2#0', src
quotes = build_quotes('Бюджет токенов промпта ограничен.', [hit('d1#0', 1.0)])
assert quotes and quotes[0].chunk_id == 'd1#0', quotes
print('ok')
PYEOF
"

# 37: режим «не знаю» — при слабом контексте LLM НЕ вызывается, источников нет.
check "RAG7: режим «не знаю» без вызова LLM" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.config import RagConfig
from rag.corpus import discover
from rag.embedding import HashingEmbedder
from rag.index import RagIndex
from rag.retrieval import Retriever
from rag.service import RagService
cfg = RagConfig.default()
emb = HashingEmbedder(dim=256)
svc = RagService(cfg)
idx = RagIndex(cfg); idx.ingest(discover(None, cfg.corpus), cfg, emb)
svc._index = idx; svc._loaded = True; svc._embedder = emb
svc._retriever = Retriever(idx, cfg, emb)
calls = {'n': 0}
def llm(messages):
    calls['n'] += 1
    return 'ответ'
ans = svc.answer('квантовые киты в борще', use_rag=True, threshold=0.99, llm=llm)
assert ans.verdict == 'insufficient', ans.verdict
assert ans.sources == () and ans.quotes == ()
assert calls['n'] == 0, calls
print('ok')
PYEOF
"

# 38: --rag-ask (mock) → ответ + источники + цитаты (пропуск без индекса).
check "RAG7: --rag-ask даёт ответ + источники + цитаты (mock)" bash -c "
  if [ ! -f '$KOD/rag/index/meta.json' ]; then echo 'индекс отсутствует — пропуск'; exit 0; fi
  OUT=\$(cd '$KOD' && API_KEY=test-key '$PY' Kod.py --rag-ask 'как считается бюджет токенов' --mock 2>&1)
  echo \"\$OUT\" | grep -q '\[RAG\] Источники' || { echo 'нет источников'; exit 1; }
  echo \"\$OUT\" | grep -q '\[RAG\] Цитаты' || { echo 'нет цитат'; exit 1; }
"

# 39: --rag-verify (mock) → источники/цитаты 10/10 на контрольных вопросах.
check "RAG7: --rag-verify источники/цитаты 10/10 (mock)" bash -c "
  if [ ! -f '$KOD/rag/index/meta.json' ]; then echo 'индекс отсутствует — пропуск'; exit 0; fi
  OUT=\$(cd '$KOD' && API_KEY=test-key '$PY' Kod.py --rag-verify --mock 2>&1)
  echo \"\$OUT\" | grep -q 'Источники: \*\*10/10\*\*' || { echo 'источники не 10/10'; exit 1; }
  echo \"\$OUT\" | grep -q 'Цитаты: \*\*10/10\*\*' || { echo 'цитаты не 10/10'; exit 1; }
"

# 40: --rag-ask с высоким порогом → «не знаю» (insufficient) на уровне CLI.
check "RAG7: --rag-ask с высоким порогом → «не знаю»" bash -c "
  if [ ! -f '$KOD/rag/index/meta.json' ]; then echo 'индекс отсутствует — пропуск'; exit 0; fi
  OUT=\$(cd '$KOD' && API_KEY=test-key '$PY' Kod.py --rag-ask 'квантовые киты в борще' --rag-threshold 0.99 --mock 2>&1)
  echo \"\$OUT\" | grep -q 'insufficient' || { echo 'нет insufficient'; exit 1; }
  echo \"\$OUT\" | grep -q 'нет ответа' || { echo 'нет сообщения «не знаю»'; exit 1; }
"

# 41: 4 режима ответа (часть 1: сравнение с/без RAG + фильтр + rewrite).
check "RAG7: 4 режима ответа (no_rag/rag/rag_filter/rag_filter_rewrite)" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from rag.compare import ANSWER_MODES
assert ANSWER_MODES == ('no_rag', 'rag', 'rag_filter', 'rag_filter_rewrite'), ANSWER_MODES
print('ok')
PYEOF
"

# 42: WorkingMemory расширена (goal/terms/clarifications) и переживает перезапуск.
check "RAG7: WorkingMemory round-trip (goal/terms/clarifications)" bash -c "
  '$PY' - <<'PYEOF'
import sys, tempfile, os
sys.path.insert(0, '$KOD')
from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from memory.base import MemoryContext
tmp = tempfile.mkdtemp(prefix='acc_wm_', dir='$TMP')
store = Store(os.path.join(tmp, 'users'), profile_repo=ProfileRepository(os.path.join(tmp, 'p.db')))
mem = MemoryManager(default_layers(store))
ctx = MemoryContext('u', 't', 's')
mem.remember('working', ctx, content={'goal': 'разобраться с бюджетом'}, source='system')
mem.remember('working', ctx, content={'terms': {'RRF': 'reciprocal rank fusion'}}, source='system')
mem.remember('working', ctx, content={'clarifications': 'именно про промпт'}, source='system')
data = store.read_working('u', 't')
assert data['goal'] == 'разобраться с бюджетом'
assert data['terms']['RRF'] == 'reciprocal rank fusion'
block = MemoryManager(default_layers(store)).layers['working'].as_prompt_block(ctx)
assert 'Цель диалога:' in block and 'Термины:' in block and 'Уточнения:' in block
print('ok')
PYEOF
"

# 43: 2 длинных диалоговых сценария (10–15 сообщений) прогоняются с RAG (mock).
check "RAG7: 2 длинных сценария (dialog_runner, mock)" bash -c "
  if [ ! -f '$KOD/rag/index/meta.json' ]; then echo 'индекс отсутствует — пропуск'; exit 0; fi
  test -s '$KOD/dev/tests_debug/scenario/scen_dialog_A.md' || { echo 'нет сценария A'; exit 1; }
  test -s '$KOD/dev/tests_debug/scenario/scen_dialog_B.md' || { echo 'нет сценария B'; exit 1; }
  cd '$KOD' && API_KEY=test-key '$PY' dev/tests_debug/dialog_runner.py --report '$TMP/dialog.md' 2>&1 | grep -q 'DIALOG OK'
"

# --- Ревизия 8: локальные LLM, RAG-контур, фасад, шлюз, доступ (этап 12, +15: 44..58) ---

# 44: реестр моделей импортируется; models.json валиден; ≥2 моделей.
check "R8: реестр моделей + models.json (≥2 моделей)" bash -c "
  '$PY' - <<'PYEOF'
import sys, json
sys.path.insert(0, '$KOD')
from core.model_registry import ModelRegistry
reg = ModelRegistry('$KOD/models.json')
assert len(reg.list()) >= 2, [s.id for s in reg.list()]
raw = json.load(open('$KOD/models.json', encoding='utf-8'))
assert raw.get('models'), 'нет секции models'
assert reg.current_id, 'нет текущей модели'
print('ok')
PYEOF
"

# 45: /model list печатает ≥2 модели и отметку текущей.
check "R8: --model-list печатает ≥2 модели" bash -c "
  OUT=\$('$PY' '$KOD/Kod.py' --model-list 2>&1)
  echo \"\$OUT\" | grep -q 'Всего:' || { echo 'нет заголовка'; exit 1; }
  N=\$(echo \"\$OUT\" | grep -cE '^[[:space:]]+[* ] (cloud|lmstudio|ollama|mock):')
  [ \"\$N\" -ge 2 ] || { echo \"моделей: \$N\"; exit 1; }
"

# 46: подпись модели есть в баннере сессии (видимость модели).
check "R8: подпись модели в баннере сессии" bash -c "
  '$PY' - <<'PYEOF'
import sys, os, tempfile
sys.path.insert(0, '$KOD')
sys.argv = ['$KOD/Kod.py']
import Kod
from core.agent import Agent
from core.llm_client import MockClient
from core.model_registry import ModelRegistry
from core.prompt_builder import PromptBuilder
from memory.manager import MemoryManager, default_layers
from storage.store import Store
tmp = tempfile.mkdtemp(dir='$TMP')
store = Store(os.path.join(tmp, 's'))
mem = MemoryManager(default_layers(store), log=lambda l: None)
agent = Agent(MockClient(name='Mock'), mem, PromptBuilder('sys'), store, user_id='t')
reg = ModelRegistry('$KOD/models.json')
agent.set_model(MockClient(name='Mock'), label=reg.current().display())
agent.model_registry = reg
banner = Kod.model_banner(agent)
assert 'cloud/' in banner, banner
print('ok')
PYEOF
"

# 47: без --model промпт байт-в-байт прежний (регрессия).
check "R8: без --model промпт байт-в-байт прежний" bash -c "
  '$PY' '$KOD/dev/tests_debug/unit_runner.py' test_model_switch 2>&1 | grep -q '0 FAIL'
"

# 48: субагент завершается и пишет лог с подписью модели.
check "R8: субагент → лог с подписью модели" bash -c "
  '$PY' - <<'PYEOF'
import sys, os, tempfile
sys.path.insert(0, '$KOD')
import core.subagents as mod
from core.subagents import SubagentRunner
from core.model_registry import ModelRegistry
class FakePopen:
    def __init__(self, command, **k):
        self.pid = 1; self.returncode = 0
        lp = command[command.index('--log') + 1]
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        open(lp, 'w', encoding='utf-8').write('[Сессия] модель: lmstudio/test\n')
    def communicate(self, timeout=None): return ('ok', None)
    def poll(self): return 0
tmp = tempfile.mkdtemp(dir='$TMP')
orig = mod.subprocess.Popen; mod.subprocess.Popen = FakePopen
try:
    r = SubagentRunner('$KOD', registry=ModelRegistry('$KOD/models.json'),
                       stages_dir=os.path.join(tmp, 'stages'), python='/usr/bin/python3')
    res = r.run('задача', service='lmstudio')
finally:
    mod.subprocess.Popen = orig
assert res['status'] == 'ok'
assert 'lmstudio/' in open(res['log'], encoding='utf-8').read()
print('ok')
PYEOF
"

# 49: --local-gen выбирает локальную модель (не облако).
check "R8: --local-gen выбирает локальную модель" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
from core.model_registry import ModelRegistry
reg = ModelRegistry('$KOD/models.json')
local = next((s for s in reg.list(role='chat') if s.local), None)
assert local is not None and local.service in ('lmstudio', 'ollama'), local
src = open('$KOD/Kod.py', encoding='utf-8').read()
assert 'if args.local_gen' in src and 's.local' in src
print('ok')
PYEOF
"

# 50: сравнение генераторов содержит три оси (качество/скорость/стабильность).
check "R8: сравнение генераторов — три оси" bash -c "
  grep -q 'трём осям' '$KOD/rag/compare.py' \
    && grep -q 'Качество' '$KOD/rag/compare.py' \
    && grep -q 'Скорость' '$KOD/rag/compare.py' \
    && grep -q 'Стабильность' '$KOD/rag/compare.py'
"

# 51: профиль параметров попадает в тело запроса к модели (LM Studio).
check "R8: профиль параметров в теле запроса" bash -c "
  '$PY' - <<'PYEOF'
import sys
sys.path.insert(0, '$KOD')
import core.llm_client as mod
from core.llm_client import OpenAICompatClient
cap = {}
class R:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return {'choices': [{'message': {'content': 'ok'}}]}
def fp(url, json=None, timeout=None):
    cap['j'] = json; return R()
orig = mod.requests.post; mod.requests.post = fp
try:
    c = OpenAICompatClient('http://127.0.0.1:1234', 'm', max_tokens=700,
                           params={'temperature': 0.1, 'top_p': 0.9})
    c.complete([{'role': 'user', 'content': 'x'}])
finally:
    mod.requests.post = orig
assert cap['j']['temperature'] == 0.1
assert cap['j']['max_tokens'] == 700
assert cap['j']['top_p'] == 0.9
print('ok')
PYEOF
"

# 52: отчёт «до/после» оптимизации существует.
check "R8: отчёт «до/после» оптимизации есть" test -s "$KOD/dev/logs_reports/stages/optimize_before_after.md"

# 53: фасад — /ask отвечает, /models отдаёт список, есть поле model (mock, без сети).
check "R8: фасад /ask+/models (mock)" bash -c "
  '$PY' - <<'PYEOF'
import sys, os, tempfile
sys.path.insert(0, '$KOD')
sys.argv = [os.path.join('$KOD', 'serve.py')]
import serve
serve._agents.clear(); serve._runtime.update(rag=False, mock=True, model=None)
serve.app.config['TESTING'] = True
c = serve.app.test_client()
r = c.get('/models')
assert r.status_code == 200
data = r.get_json()
assert data['current'] and any(m['id'].startswith('lmstudio:') for m in data['models'])
r2 = c.post('/ask', json={'user': 'acc_facade', 'text': 'привет'})
assert r2.status_code == 200
assert r2.get_json()['model']
print('ok')
PYEOF
"

# 54: шлюз требует входа и работает под лимитом (Flask test client, заглушка).
check "R8: шлюз — вход обязателен + лимит 6/мин" bash -c "
  '$PY' '$KOD/dev/tests_debug/unit_runner.py' test_gateway 2>&1 | grep -q '0 FAIL'
"

# 55: юнит туннеля — авторестарт + собственная SSH-сессия (статическая проверка).
check "R8: юнит туннеля (Restart=always, ControlMaster=no)" bash -c "
  grep -q 'Restart=always' '$KOD/dev/vps/units/ai9-tunnel.service' \
    && grep -q 'ControlMaster=no' '$KOD/dev/vps/units/ai9-tunnel.service' \
    && grep -q 'ControlPath=none' '$KOD/dev/vps/units/ai9-tunnel.service'
"

# 56: регрессия MCP на VPS — порты 8000/8010/8020 в services.list сохранены.
check "R8: MCP-порты 8000/8010/8020 сохранены" bash -c "
  grep -q '8000' '$KOD/dev/vps/services.list' \
    && grep -q '8010' '$KOD/dev/vps/services.list' \
    && grep -q '8020' '$KOD/dev/vps/services.list'
"

# 57: секретов нет в конфигах (models.json, gateway.json, .env.example) и в логах.
check "R8: секретов нет в конфигах" bash -c "
  if grep -rE 'sk-[A-Za-z0-9]{10,}' '$KOD/models.json' '$KOD/gateway/gateway.json' '$KOD/.env.example' 2>/dev/null; then
    echo 'найден ключ sk-'; exit 1; fi
  if grep -rE 'API_KEY=[A-Za-z0-9]{20,}' '$KOD/models.json' '$KOD/gateway/gateway.json' 2>/dev/null; then
    echo 'найден API_KEY'; exit 1; fi
  if grep -qE 'sk-[A-Za-z0-9]{10,}|Bearer [A-Za-z0-9]{20,}' '$KOD/Den_log.md' 2>/dev/null; then
    echo 'секрет в Den_log.md'; exit 1; fi
"

# 58: 4 сценария ручной демонстрации на месте и непусты.
check "R8: 4 сценария демонстрации на месте" bash -c "
  for f in scen_local_llm scen_rag_local scen_optimize scen_access; do
    test -s '$KOD/dev/tests_debug/scenario/'\$f'.md' || { echo \"нет \$f.md\"; exit 1; }
  done
"

# ИтОГ

echo ""
echo "ИТОГ: $PASS из $TOTAL зелёные (FAIL=$FAIL)"



rm -rf "$TMP"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
