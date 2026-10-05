#!/usr/bin/env bash
# deploy_services.sh — идемпотентный деплой пользовательских systemd-юнитов MCP.
# Этап 1 (И2б). Запуск НА VPS, БЕЗ sudo:  bash dev/vps/deploy_services.sh
#
# Делает для каждой строки services.list:
#   1) кладёт unit из dev/vps/units/ в ~/.config/systemd/user/;
#   2) systemctl --user daemon-reload;
#   3) enable --now + restart (свежий код после правки);
#   4) печатает is-active и порт.
#
# Повторный запуск безопасен (cp -f, restart). Пароль sudo не запрашивается.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"   # корень AI_9
UNITS_SRC="$REPO/dev/vps/units"
LIST="$REPO/dev/vps/services.list"
UNITS_DST="$HOME/.config/systemd/user"

# Для не-интерактивного SSH (без логин-сессии) нужен runtime-каталог и шина D-Bus
# (риск из migr_plan.md §8: «systemctl --user не поднимается по SSH»).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

[ -f "$LIST" ] || { echo "deploy_services: нет $LIST" >&2; exit 1; }
mkdir -p "$UNITS_DST"

# 1) установка unit-файлов.
# `|| [ -n "$name" ]` — иначе последняя строка без завершающего \n теряется.
while IFS=: read -r name port || [ -n "${name:-}" ]; do
  [ -n "${name:-}" ] || continue
  case "$name" in \#*) continue ;; esac
  src="$UNITS_SRC/$name.service"
  [ -f "$src" ] || { echo "deploy_services: нет юнита $src" >&2; exit 1; }
  cp -f "$src" "$UNITS_DST/$name.service"
  echo "→ установлен $name.service"
done < "$LIST"

# 2) перечитать юниты.
systemctl --user daemon-reload

# 3+4) включить, перезапустить, показать статус.
echo "— статус —"
while IFS=: read -r name port || [ -n "${name:-}" ]; do
  [ -n "${name:-}" ] || continue
  case "$name" in \#*) continue ;; esac
  systemctl --user enable --now "$name.service" >/dev/null 2>&1 || true
  systemctl --user restart "$name.service" || true
  state="$(systemctl --user is-active "$name.service" 2>/dev/null || true)"
  printf '%-22s %-8s :%s\n' "$name" "${state:-unknown}" "$port"
done < "$LIST"


