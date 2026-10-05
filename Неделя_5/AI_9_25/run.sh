#!/bin/bash
# Запуск Kod.py с активацией виртуального окружения (канон донора).
# Работает из любого каталога: cd к каталогу скрипта, затем venv корня AI_9.
cd "$(dirname "$0")"
source .venv/bin/activate
python Kod.py "$@"