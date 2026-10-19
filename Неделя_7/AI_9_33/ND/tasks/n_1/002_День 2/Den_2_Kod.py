import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Загрузка переменных из .env
# ---------------------------------------------------------------------------
load_dotenv()

api_key = os.getenv("API_KEY")
if not api_key:
    raise RuntimeError(
        "Переменная API_KEY не найдена. "
        "Добавьте API-ключ в файл .env"
    )

# ---------------------------------------------------------------------------
# Константы API
# ---------------------------------------------------------------------------
URL = "https://routerai.ru/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
MODEL = "stepfun/step-3.5-flash"

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def build_system_prompt(mode: str, word_limit: int = 100) -> str:
    """Возвращает системный промпт в зависимости от режима."""
    base = "Ты полезный ассистент. Отвечай на русском языке."
    if mode == "json":
        base += (
            " Формат ответа: JSON с полями ingredients (массив объектов с полями "
            "name, weight, order) и steps (массив строк). "
            f"Используй не более {word_limit} слов в ответе."
        )
    return base


def validate_json_response(text: str) -> bool:
    """Проверяет, что ответ содержит валидный JSON с ожидаемыми полями."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return False
        # Ожидаем поля ingredients и steps
        if "ingredients" not in data or "steps" not in data:
            return False
        if not isinstance(data["ingredients"], list) or not isinstance(data["steps"], list):
            return False
        # Проверяем структуру элементов ingredients
        for item in data["ingredients"]:
            if not isinstance(item, dict):
                return False
            if "name" not in item or "weight" not in item or "order" not in item:
                return False
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def send_request(messages: list, max_tokens: int = 500, stop: list | None = None,
                 temperature: float = 0.7) -> str:
    """Отправляет запрос к API и возвращает текст ответа."""
    data: dict = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if stop:
        data["stop"] = stop

    try:
        response = requests.post(URL, headers=HEADERS, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"] or ""
        return content
    except requests.exceptions.HTTPError as exc:
        print(f"  [Ошибка HTTP] {exc}")
    except requests.exceptions.RequestException as exc:
        print(f"  [Ошибка сети] {exc}")
    except (KeyError, IndexError, ValueError) as exc:
        print(f"  [Ошибка разбора ответа] {exc}")
    return ""


def run_mode(label: str, mode: str, user_query: str, stop_seq: list | None = None,
             temperature: float = 0.7, max_tokens: int = 500) -> None:
    """Запускает один режим, выводит заголовок и ответ."""
    print(f"\n{'=' * 50}")
    print(f"  {label}")
    print(f"{'=' * 50}")

    word_limit = 100 if mode == "json" else None
    system_content = build_system_prompt(mode, word_limit=word_limit)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_query},
    ]

    response = send_request(messages, max_tokens=max_tokens, stop=stop_seq,
                            temperature=temperature)

    if mode == "json":
        if response and validate_json_response(response):
            # Красиво форматируем JSON
            formatted = json.dumps(json.loads(response), ensure_ascii=False, indent=2)
            print(f"Бот: {formatted}")
        else:
            print(f"Бот: {response}")
            if response:
                print("  ⚠️  Предупреждение: ответ не соответствует ожидаемой JSON-структуре")
    else:
        print(f"Бот: {response}")


# ---------------------------------------------------------------------------
# Интерактивный режим
# ---------------------------------------------------------------------------
def run_interactive(temperature: float = 0.7, max_tokens: int = 500) -> None:
    """Запускает интерактивный режим с вводом пользователя."""
    print("🤖 Сравнение форматов ответа")
    print("Введите «выход» для завершения.\n")

    while True:
        user_input = input("Вы: ").strip()

        if user_input.lower() == "выход":
            print("До свидания!")
            break

        if not user_input:
            continue

        # --- Свободный режим ---
        run_mode("=== Свободный режим (без ограничений) ===", "free", user_input,
                 temperature=temperature, max_tokens=max_tokens)

        # --- JSON-режим ---
        run_mode("=== JSON-режим (строгий формат + валидация) ===", "json", user_input,
                 temperature=temperature, max_tokens=max_tokens)

        # --- Stop sequence ---
        run_mode("=== Stop sequence режим ===", "free", user_input,
                 stop=["Конец ответа."], temperature=temperature, max_tokens=max_tokens)

        print(f"\n{'=' * 50}")
        print("  ✅ Сравнение завершено.")
        print(f"{'=' * 50}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сравнение режимов контроля ответа LLM через RouterAI API"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Текст запроса к модели (без флагов — интерактивный режим)",
    )
    parser.add_argument(
        "--free",
        action="store_true",
        help="Свободный режим — без ограничений",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="JSON-режим — строгий формат ответа с валидацией",
    )
    parser.add_argument(
        "--stop-sequence",
        type=str,
        metavar="TEXT",
        help="Режим со стоп-последовательностью (модель остановится при её обнаружении)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Запустить все три режима для сравнения",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        metavar="VALUE",
        help="Температура генерации (0.0–2.0, по умолчанию: 0.7)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=500,
        metavar="N",
        help="Максимальное количество токенов в ответе (по умолчанию: 500)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Если query не указан — интерактивный режим
    if args.query is None:
        run_interactive(temperature=args.temperature, max_tokens=args.max_tokens)
        return

    query = args.query

    # Если указан --all — запускаем все три режима для сравнения
    if args.all:
        args.free = True
        args.json_mode = True
        args.stop_sequence = "Конец ответа."
    # Если ни один режим не указан — запускаем все три для сравнения
    elif not args.free and not args.json_mode and not args.stop_sequence:
        args.free = True
        args.json_mode = True
        args.stop_sequence = "Конец ответа."

    # --- Свободный режим ---
    if args.free:
        run_mode("=== Свободный режим (без ограничений) ===", "free", query,
                 temperature=args.temperature, max_tokens=args.max_tokens)

    # --- JSON-режим ---
    if args.json_mode:
        run_mode("=== JSON-режим (строгий формат + валидация) ===", "json", query,
                 temperature=args.temperature, max_tokens=args.max_tokens)

    # --- Stop sequence ---
    if args.stop_sequence:
        run_mode(
            "=== Stop sequence режим ===",
            "free",
            query,
            stop=[args.stop_sequence],
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

    print(f"\n{'=' * 50}")
    print("  ✅ Сравнение завершено.")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
