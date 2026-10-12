import argparse
import json
import os
import sys
import time

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
MAX_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 60

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def send_request(messages: list, max_tokens: int = 500,
                 temperature: float = 0.7) -> str:
    """Отправляет запрос к API и возвращает текст ответа.
    
    При превышении лимита токенов (HTTP 429) повторяет запрос после паузы.
    """
    data: dict = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(URL, headers=HEADERS, json=data, timeout=60)
            
            # Обработка превышения лимита токенов в минуту
            if response.status_code == 429:
                try:
                    body = response.json()
                    error_msg = json.dumps(body).lower()
                except (json.JSONDecodeError, ValueError):
                    error_msg = ""
                
                if "rate_limit" in error_msg or "too_many" in error_msg or "limit" in error_msg:
                    if attempt == MAX_RETRIES - 1:
                        raise RuntimeError(
                            "Превышен лимит API после повторной попытки. "
                            "Подождите минуту и попробуйте снова."
                        )
                    print("  ⏳ Превышен минутный лимит. Повтор через 60 сек...")
                    time.sleep(RATE_LIMIT_WAIT_SECONDS)
                    continue
                response.raise_for_status()
            
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"] or ""
            return content
            
        except requests.exceptions.HTTPError as exc:
            if exc.response and exc.response.status_code == 429:
                if attempt == MAX_RETRIES - 1:
                    raise
                print("  ⏳ Превышен лимит API. Повтор через 60 сек...")
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            print(f"  [Ошибка HTTP] {exc}")
            return ""
        except requests.exceptions.RequestException as exc:
            print(f"  [Ошибка сети] {exc}")
            return ""
        except (KeyError, IndexError, ValueError) as exc:
            print(f"  [Ошибка разбора ответа] {exc}")
            return ""
    
    return ""


def run_with_temperature(user_query: str, temperature: float,
                         max_tokens: int = 500) -> str:
    """Отправляет запрос с заданной температурой."""
    messages = [
        {
            "role": "system",
            "content": "Ты полезный ассистент. Отвечай на русском языке.",
        },
        {"role": "user", "content": user_query},
    ]
    return send_request(messages, max_tokens=max_tokens, temperature=temperature)


def run_comparison(user_query: str, temp_03_answer: str,
                   temp_07_answer: str, temp_13_answer: str,
                   max_tokens: int = 1024) -> str:
    """Финальное сравнение трёх ответов с разной температурой.
    
    Использует подход LLM-as-a-Judge: модель оценивает все ответы по критериям.
    """
    comparison_prompt = (
        "Ты независимый эксперт по оценке качества ответов LLM. "
        "Сравни три ответа на одну и ту же задачу, полученных с разной температурой генерации. "
        "Оцени каждый ответ и определи, какая температура лучше подходит для данного типа задачи.\n\n"
        "Критерии оценки:\n"
        "1. Точность и логическая корректность результата\n"
        "2. Креативность и оригинальность подхода\n"
        "3. Разнообразие формулировок\n"
        "4. Пригодность ответа для данного типа задачи\n\n"
    )
    
    comparison_prompt += (
        f"Задача: {user_query}\n\n"
        f"1. temperature=0.3 (детерминированный):\n{temp_03_answer}\n\n"
        f"2. temperature=0.7 (баланс):\n{temp_07_answer}\n\n"
        f"3. temperature=1.3 (высокая креативность):\n{temp_13_answer}\n\n"
        "Для каждого ответа кратко оцени по критериям выше.\n"
        "Затем сформулируй выводы:\n"
        "- Для каких типов задач лучше подходит temperature=0.3\n"
        "- Для каких типов задач лучше подходит temperature=0.7\n"
        "- Для каких типов задач лучше подходит temperature=1.3\n"
        "Не оценивай длину текста как признак точности."
    )
    
    messages = [
        {
            "role": "system",
            "content": "Ты независимый эксперт по оценке качества ответов LLM. Отвечай на русском языке.",
        },
        {"role": "user", "content": comparison_prompt},
    ]
    
    return send_request(messages, max_tokens=max_tokens, temperature=temperature)


def print_and_return(label: str, content: str) -> str:
    """Выводит заголовок и содержимое, возвращает содержимое для дальнейшего использования."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"Бот: {content}")
    return content


# ---------------------------------------------------------------------------
# Интерактивный режим
# ---------------------------------------------------------------------------
def run_interactive(max_tokens: int = 500) -> None:
    """Запускает интерактивный режим с вводом пользователя."""
    print("🤖 Сравнение температур генерации")
    print("Введите «выход» для завершения.\n")

    while True:
        user_input = input("Вы: ").strip()

        if user_input.lower() == "выход":
            print("До свидания!")
            break

        if not user_input:
            continue

        # --- Температура 0.3 ---
        temp_03_answer = print_and_return(
            "=== Температура 0.3 (детерминированный) ===",
            run_with_temperature(user_input, temperature=0.3, max_tokens=max_tokens)
        )

        # --- Температура 0.7 ---
        temp_07_answer = print_and_return(
            "=== Температура 0.7 (баланс) ===",
            run_with_temperature(user_input, temperature=0.7, max_tokens=max_tokens)
        )

        # --- Температура 1.3 ---
        temp_13_answer = print_and_return(
            "=== Температура 1.3 (высокая креативность) ===",
            run_with_temperature(user_input, temperature=1.3, max_tokens=max_tokens)
        )

        # --- Финальное сравнение ---
        print(f"\n{'=' * 60}")
        print("  📊 Итоговое сравнение")
        print(f"{'=' * 60}")
        comparison = run_comparison(
            user_input, temp_03_answer, temp_07_answer, temp_13_answer,
            max_tokens=1024
        )
        print(f"\nБот: {comparison}")

        print(f"\n{'=' * 60}")
        print("  ✅ Сравнение завершено.")
        print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сравнение температур генерации LLM через RouterAI API"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Текст запроса к модели (без флагов — интерактивный режим)",
    )
    parser.add_argument(
        "--temp-0.3",
        action="store_true",
        dest="temp_0_3",
        help="Температура 0.3 — детерминированный ответ",
    )
    parser.add_argument(
        "--temp-0.7",
        action="store_true",
        dest="temp_0_7",
        help="Температура 0.7 — баланс точности и разнообразия",
    )
    parser.add_argument(
        "--temp-1.3",
        action="store_true",
        dest="temp_1_3",
        help="Температура 1.3 — высокая креативность",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Запустить все три температуры для сравнения",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Запустить финальное сравнение всех способов",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        metavar="VALUE",
        help="Произвольная температура (0.0–2.0, по умолчанию: нет)",
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
        run_interactive(max_tokens=args.max_tokens)
        return

    query = args.query

    # Если указан --all — запускаем все три температуры + сравнение
    if args.all:
        args.temp_0_3 = True
        args.temp_0_7 = True
        args.temp_1_3 = True
        args.compare = True
    # Если ни один способ не указан — запускаем все три + сравнение
    elif not args.temp_0_3 and not args.temp_0_7 and not args.temp_1_3:
        args.temp_0_3 = True
        args.temp_0_7 = True
        args.temp_1_3 = True
        args.compare = True

    # --- Температура 0.3 ---
    temp_03_answer = ""
    if args.temp_0_3:
        temp_03_answer = print_and_return(
            "=== Температура 0.3 (детерминированный) ===",
            run_with_temperature(query, temperature=0.3, max_tokens=args.max_tokens)
        )

    # --- Температура 0.7 ---
    temp_07_answer = ""
    if args.temp_0_7:
        temp_07_answer = print_and_return(
            "=== Температура 0.7 (баланс) ===",
            run_with_temperature(query, temperature=0.7, max_tokens=args.max_tokens)
        )

    # --- Температура 1.3 ---
    temp_13_answer = ""
    if args.temp_1_3:
        temp_13_answer = print_and_return(
            "=== Температура 1.3 (высокая креативность) ===",
            run_with_temperature(query, temperature=1.3, max_tokens=args.max_tokens)
        )

    # --- Финальное сравнение ---
    if args.compare:
        print(f"\n{'=' * 60}")
        print("  📊 Итоговое сравнение")
        print(f"{'=' * 60}")
        comparison = run_comparison(
            query, temp_03_answer, temp_07_answer, temp_13_answer,
            max_tokens=1024
        )
        print(f"\nБот: {comparison}")

    # --- Произвольная температура ---
    if args.temperature is not None:
        temp = args.temperature
        if temp < 0.0 or temp > 2.0:
            print("  [Ошибка] Температура должна быть в диапазоне 0.0–2.0")
            return
        print_and_return(
            f"=== Температура {temp} (произвольная) ===",
            run_with_temperature(query, temperature=temp, max_tokens=args.max_tokens)
        )

    print(f"\n{'=' * 60}")
    print("  ✅ Сравнение завершено.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
