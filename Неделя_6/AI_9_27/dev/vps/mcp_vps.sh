#!/usr/bin/env bash
# mcp_vps.sh — операторский контур отладки MCP-серверов на VPS (Этап 2, И4).
#
# ЛОКАЛЬНЫЙ скрипт: работает с машины оператора через `ssh mcp-vps` и `curl`.
# Продуктом НЕ импортируется, в acceptance-гейт НЕ входит (мост «оператор ↔ VPS»).
# Зависимости: bash, curl, ssh, python3 (для разбора JSON) — БЕЗ jq.
#
# Использование:
#   ./dev/vps/mcp_vps.sh status                 # юнит + порт на VPS
#   ./dev/vps/mcp_vps.sh probe  [port]          # handshake + tools/list (по умолч. 8000)
#   ./dev/vps/mcp_vps.sh tools  [port]          # то же, что probe (псевдоним)
#   ./dev/vps/mcp_vps.sh call <port> <tool> <json>   # tools/call
#   ./dev/vps/mcp_vps.sh log    [unit]          # журнал systemd (по умолч. mcp-time-server)
#   ./dev/vps/mcp_vps.sh deploy                 # deploy_services.sh на VPS (по SSH)
#   ./dev/vps/mcp_vps.sh tunnel [port]          # SSH-туннель localhost:port → VPS:port
#
# Расшифровки probe/call сохраняются в dev/vps/evidence/.
set -euo pipefail

HOST="${MCP_VPS_HOST:-mcp-vps}"          # алиас из ~/.ssh/config
IP="${MCP_VPS_IP:-91.188.212.77}"        # публичный адрес (для curl снаружи)
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
EVID="$REPO/dev/vps/evidence"
mkdir -p "$EVID"

stamp() { date -u +%Y%m%dT%H%M%SZ; }

# --- JSON-RPC через python3 (без jq) -----------------------------------------
# rpc <port> <method> <params-json> [session-id]  → печатает тело ответа
rpc() {
  local port="$1" method="$2" params="$3" sid="${4:-}"
  local url="http://${IP}:${port}/mcp"
  local hdr=(-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream')
  [ -n "$sid" ] && hdr+=(-H "mcp-session-id: $sid")
  curl -sS -X POST "$url" "${hdr[@]}" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"${method}\",\"params\":${params}}"
}

# init_session <port> → печатает mcp-session-id (в stderr — заголовки)
init_session() {
  local port="$1"
  local url="http://${IP}:${port}/mcp"
  curl -sS -D - -o /dev/null -X POST "$url" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"mcp_vps","version":"0"}}}' \
    | tr -d '\r' | awk 'tolower($1)=="mcp-session-id:"{print $2}'
}

notify_initialized() {
  local port="$1" sid="$2"
  local url="http://${IP}:${port}/mcp"
  curl -sS -X POST "$url" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H "mcp-session-id: $sid" \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null || true
}

# --- подкоманды ---------------------------------------------------------------
cmd_status() {
  echo "== VPS $HOST ($IP) =="
  ssh -o BatchMode=yes "$HOST" '
    for u in mcp-time-server mcp-scheduler-server mcp-pipeline-server; do
      printf "%-24s %s\n" "$u" "$(systemctl --user is-active "$u" 2>/dev/null || echo -)"
    done
    echo "-- порты --"
    ss -ltnp 2>/dev/null | grep -E ":(8000|8010|8020)\b" || echo "(8000/8010/8020 не слушают)"
  '
}

cmd_probe() {
  local port="${1:-8000}"
  local out="$EVID/probe_${port}_$(stamp).txt"
  {
    echo "# probe :$port  $(date -u +%FT%TZ)"
    local sid; sid="$(init_session "$port")"
    echo "mcp-session-id: ${sid:-<пусто>}"
    if [ -z "$sid" ]; then
      echo "!! initialize не вернул session-id — сервер недоступен или Host не разрешён"
      return 1
    fi
    notify_initialized "$port" "$sid"
    echo "-- tools/list --"
    rpc "$port" "tools/list" "{}" "$sid"
  } | tee "$out"
  echo ""
  echo "→ расшифровка: $out"
}

cmd_call() {
  local port="$1" tool="$2" args="$3"
  local out="$EVID/call_${port}_${tool}_$(stamp).txt"
  {
    echo "# call :$port $tool $args  $(date -u +%FT%TZ)"
    local sid; sid="$(init_session "$port")"
    echo "mcp-session-id: ${sid:-<пусто>}"
    [ -z "$sid" ] && { echo "!! нет session-id"; return 1; }
    notify_initialized "$port" "$sid"
    echo "-- tools/call --"
    rpc "$port" "tools/call" "{\"name\":\"${tool}\",\"arguments\":${args}}" "$sid"
  } | tee "$out"
  echo ""
  echo "→ расшифровка: $out"
}

cmd_log() {
  local unit="${1:-mcp-time-server}"
  ssh -o BatchMode=yes "$HOST" "journalctl --user -u '$unit' -n 40 --no-pager"
}

cmd_deploy() {
  ssh -o BatchMode=yes "$HOST" 'cd /home/t/doc/AI_9 && git pull --ff-only && bash dev/vps/deploy_services.sh'
}

cmd_tunnel() {
  local port="${1:-8000}"
  echo "Туннель: localhost:$port → $HOST:$port (Ctrl-C для выхода)"
  ssh -N -L "${port}:localhost:${port}" "$HOST"
}

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

case "${1:-}" in
  status) cmd_status ;;
  probe|tools) cmd_probe "${2:-8000}" ;;
  call) [ $# -ge 4 ] || usage; cmd_call "$2" "$3" "$4" ;;
  log) cmd_log "${2:-mcp-time-server}" ;;
  deploy) cmd_deploy ;;
  tunnel) cmd_tunnel "${2:-8000}" ;;
  *) usage ;;
esac
