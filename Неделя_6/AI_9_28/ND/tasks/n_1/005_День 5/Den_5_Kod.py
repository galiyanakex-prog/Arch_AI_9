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
MAX_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 60

# ---------------------------------------------------------------------------
# Прайс-лист моделей (routerai.ru, ₽ за 1M токенов)
# ---------------------------------------------------------------------------
MODELS = {
    "weak": {
        "id": "sao10k/l3-lunaris-8b",
        "name": "Llama 3 8B Lunaris",
        "price_input": 4.50,
        "price_output": 5.63,
    },
    "medium": {
        "id": "openai/gpt-5-nano",
        "name": "GPT-5 Nano",
        "price_input": 5.65,
        "price_output": 45.00,
    },
    "strong": {
        "id": "deepseek/deepseek-v4-pro-0813",
        "name": "DeepSeek V4 Pro 0813",
        "price_input": 91.00,
        "price_output": 274.00,
    },
}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def send_request(messages: list, model: str, max_tokens: int = 500,
                 temperature: float = 0.7) -> tuple[str, dict]:
    """Отправляет запрос к API и возвращает (текст ответа, метрики).

    Метрики: {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
    При превышении лимита токенов (HTTP 429) повторяет запрос после паузы.
    """
    data: dict = {
        "model": model,
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

            # Извлекаем метрики токенов
            usage = result.get("usage", {})
            metrics = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

            return content, metrics

        except requests.exceptions.HTTPError as exc:
            if exc.response and exc.response.status_code == 429:
                if attempt == MAX_RETRIES - 1:
                    raise
                print("  ⏳ Превышен лимит API. Повтор через 60 сек...")
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            print(f"  [Ошибка HTTP] {exc}")
            return "", {}
        except requests.exceptions.RequestException as exc:
            print(f"  [Ошибка сети] {exc}")
            return "", ""
        except (KeyError, IndexError, ValueError) as exc:
            print(f"  [Ошибка разбора ответа] {exc}")
            return "", {}

    return "", {}


def calculate_cost(metrics: dict, price_input: float, price_output: float) -> float:
    """Рассчитывает стоимость вызова на основе прайса и метрик."""
    if not metrics:
        return 0.0
    return (
        metrics["prompt_tokens"] * price_input / 1_000_000 +
        metrics["completion_tokens"] * price_output / 1_000_000
    )


def run_with_model(user_query: str, model_info: dict,
                   max_tokens: int = 500,
                   temperature: float = 0.7) -> tuple[str, dict, float]:
    """Отправляет запрос к модели, возвращает (ответ, метрики, стоимость)."""
    model_id = model_info["id"]
    price_input = model_info["price_input"]
    price_output = model_info["price_output"]

    messages = [
        {
            "role": "system",
            "content": "Ты полезный ассистент. Отвечай на русском языке.",
        },
        {"role": "user", "content": user_query},
    ]

    start_time = time.perf_counter()
    content, metrics = send_request(
        messages, model=model_id, max_tokens=max_tokens, temperature=temperature
    )
    elapsed = time.perf_counter() - start_time

    cost = calculate_cost(metrics, price_input, price_output)

    return content, metrics, elapsed, cost


def run_comparison(user_query: str, results: dict,
                   max_tokens: int = 1024) -> str:
    """Финальное сравнение ответов от разных моделей.

    Использует подход LLM-as-a-Judge: модель оценивает все ответы по критериям.
    """
    comparison_prompt = (
        "Ты независимый эксперт по оценке качества ответов LLM. "
        "Сравни три ответа на одну и ту же задачу, полученных от моделей разного уровня. "
        "Оцени каждый ответ и определи, какая модель лучше подходит для какого типа задач.\n\n"
        "Критерии оценки:\n"
        "1. Точность и логическая корректность результата\n"
        "2. Полнота и обоснованность рассуждений\n"
        "3. Соотношение качества ответа и ресурсов модели\n"
        "4. Пригодность ответа для данного типа задачи\n\n"
    )

    # Формируем блоки с ответами и метриками
    for level, (answer, metrics, elapsed, cost) in results.items():
        level_name = {
            "weak": "Слабая модель",
            "medium": "Средняя модель",
            "strong": "Сильная модель",
        }.get(level, level)
        comparison_prompt += (
            f"{level_name}:\n"
            f"  Время: {elapsed:.3f} сек\n"
            f"  Токены: {metrics.get('prompt_tokens', 0)} input / {metrics.get('completion_tokens', 0)} output\n"
            f"  Стоимость: {cost:.4f} ₽\n"
            f"  Ответ:\n{answer}\n\n"
        )

    comparison_prompt += (
        f"Задача: {user_query}\n\n"
        "Для каждой модели кратко оцени по критериям выше.\n"
        "Затем сформулируй выводы:\n"
        "- Для каких типов задач лучше подходит слабая модель\n"
        "- Для каких типов задач лучше подходит средняя модель\n"
        "- Для каких типов задач лучше подходит сильная модель\n"
        "- Какой компромисс между качеством, скоростью и стоимостью\n"
        "Не оценивай длину текста как признак точности."
    )

    messages = [
        {
            "role": "system",
            "content": "Ты независимый эксперт по оценке качества ответов LLM. Отвечай на русском языке.",
        },
        {"role": "user", "content": comparison_prompt},
    ]

    content, _ = send_request(
        messages, model=MODELS["strong"]["id"], max_tokens=max_tokens, temperature=0.2
    )
    return content


def format_time(seconds: float) -> str:
    """Форматирует время в секундах."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} мс"
    return f"{seconds:.3f} сек"


def format_cost(cost: float) -> str:
    """Форматирует стоимость."""
    if cost < 0.0001:
        return "< 0.0001 ₽"
    return f"{cost:.4f} ₽"


def print_and_return(label: str, content: str, metrics: dict,
                     elapsed: float, cost: float, model_name: str) -> tuple[str, dict, float, float]:
    """Выводит заголовок и содержимое, возвращает данные для дальнейшего использования."""
    print(f"\n{'=' * 60}")
    print(f"  === {model_name} ===")
    print(f"{'=' * 60}")
    print(f"Бот: {content}")
    print(f"\n  ⏱ Время: {format_time(elapsed)}")
    print(f"  🔢 Токены: {metrics.get('prompt_tokens', 0)} input / {metrics.get('completion_tokens', 0)} output")
    print(f"  💰 Стоимость: {format_cost(cost)}")
    return content, metrics, elapsed, cost


# ---------------------------------------------------------------------------
# Интерактивный режим
# ---------------------------------------------------------------------------
def run_interactive(temperature: float = 0.7, max_tokens: int = 500) -> None:
    """Запускает интерактивный режим с вводом пользователя."""
    print("🤖 Сравнение версий моделей")
    print("Введите «выход» для завершения.\n")

    while True:
        user_input = input("Вы: ").strip()

        if user_input.lower() == "выход":
            print("До свидания!")
            break

        if not user_input:
            continue

        results = {}

        # --- Слабая модель ---
        print(f"\n{'=' * 60}")
        print("  🚀 Запуск слабой модели...")
        print(f"{'=' * 60}")
        answer, metrics, elapsed, cost = run_with_model(
            user_input, MODELS["weak"], max_tokens=max_tokens, temperature=temperature
        )
        print_and_return(
            "=== Слабая модель ===", answer, metrics, elapsed, cost,
            MODELS["weak"]["name"]
        )
        results["weak"] = (answer, metrics, elapsed, cost)

        # --- Средняя модель ---
        print(f"\n{'=' * 60}")
        print("  🚀 Запуск средней модели...")
        print(f"{'=' * 60}")
        answer, metrics, elapsed, cost = run_with_model(
            user_input, MODELS["medium"], max_tokens=max_tokens, temperature=temperature
        )
        print_and_return(
            "=== Средняя модель ===", answer, metrics, elapsed, cost,
            MODELS["medium"]["name"]
        )
        results["medium"] = (answer, metrics, elapsed, cost)

        # --- Сильная модель ---
        print(f"\n{'=' * 60}")
        print("  🚀 Запуск сильной модели...")
        print(f"{'=' * 60}")
        answer, metrics, elapsed, cost = run_with_model(
            user_input, MODELS["strong"], max_tokens=max_tokens, temperature=temperature
        )
        print_and_return(
            "=== Сильная модель ===", answer, metrics, elapsed, cost,
            MODELS["strong"]["name"]
        )
        results["strong"] = (answer, metrics, elapsed, cost)

        # --- Сводная таблица ---
        print(f"\n{'=' * 60}")
        print("  📊 Сводная таблица")
        print(f"{'=' * 60}")
        print(f"  {'Модель':<25} | {'Время':<12} | {'Токены (in/out)':<18} | {'Стоимость'}")
        print(f"  {'-' * 25}-+-{'-' * 12}-+-{'-' * 18}-+-{'-' * 12}")
        for level in ["weak", "medium", "strong"]:
            answer, metrics, elapsed, cost = results[level]
            name = MODELS[level]["name"]
            in_t = metrics.get("prompt_tokens", 0)
            out_t = metrics.get("completion_tokens", 0)
            print(f"  {name:<25} | {format_time(elapsed):<12} | {in_t} / {out_t:<16} | {format_cost(cost)}")

        # --- Финальное сравнение ---
        print(f"\n{'=' * 60}")
        print("  📊 Итоговое сравнение")
        print(f"{'=' * 60}")
        comparison = run_comparison(user_input, results, max_tokens=1024)
        print(f"\nБот: {comparison}")

        print(f"\n{'=' * 60}")
        print("  ✅ Сравнение завершено.")
        print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сравнение версий моделей LLM через RouterAI API"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Текст запроса к модели (без флагов — интерактивный режим)",
    )
    parser.add_argument(
        "--weak",
        action="store_true",
        help="Слабая модель — Llama 3 8B Lunaris",
    )
    parser.add_argument(
        "--medium",
        action="store_true",
        dest="medium",
        help="Средняя модель — GPT-5 Nano",
    )
    parser.add_argument(
        "--strong",
        action="store_true",
        dest="strong",
        help="Сильная модель — DeepSeek V4 Pro",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Запустить все три модели для сравнения",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Запустить финальное сравнение всех моделей",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="ID",
        help="Произвольная модель (идентификатор из каталога routerai.ru)",
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

    # Если указан --all — запускаем все три модели + сравнение
    if args.all:
        args.weak = True
        args.medium = True
        args.strong = True
        args.compare = True
    # Если ни один уровень не указан — запускаем все три + сравнение
    elif not args.weak and not args.medium and not args.strong and not args.model:
        args.weak = True
        args.medium = True
        args.strong = True
        args.compare = True

    results = {}

    # --- Слабая модель ---
    if args.weak:
        answer, metrics, elapsed, cost = run_with_model(
            query, MODELS["weak"], max_tokens=args.max_tokens, temperature=args.temperature
        )
        print_and_return(
            "=== Слабая модель ===", answer, metrics, elapsed, cost,
            MODELS["weak"]["name"]
        )
        results["weak"] = (answer, metrics, elapsed, cost)

    # --- Средняя модель ---
    if args.medium:
        answer, metrics, elapsed, cost = run_with_model(
            query, MODELS["medium"], max_tokens=args.max_tokens, temperature=args.temperature
        )
        print_and_return(
            "=== Средняя модель ===", answer, metrics, elapsed, cost,
            MODELS["medium"]["name"]
        )
        results["medium"] = (answer, metrics, elapsed, cost)

    # --- Сильная модель ---
    if args.strong:
        answer, metrics, elapsed, cost = run_with_model(
            query, MODELS["strong"], max_tokens=args.max_tokens, temperature=args.temperature
        )
        print_and_return(
            "=== Сильная модель ===", answer, metrics, elapsed, cost,
            MODELS["strong"]["name"]
        )
        results["strong"] = (answer, metrics, elapsed, cost)

    # --- Произвольная модель ---
    if args.model is not None:
        answer, metrics, elapsed, cost = run_with_model(
            query, {"id": args.model, "price_input": 0, "price_output": 0},
            max_tokens=args.max_tokens, temperature=args.temperature
        )
        print_and_return(
            f"=== Произвольная модель: {args.model} ===",
            answer, metrics, elapsed, cost, args.model
        )

    # --- Сводная таблица (если несколько моделей) ---
    if len(results) > 1:
        print(f"\n{'=' * 60}")
        print("  📊 Сводная таблица")
        print(f"{'=' * 60}")
        print(f"  {'Модель':<25} | {'Время':<12} | {'Токены (in/out)':<18} | {'Стоимость'}")
        print(f"  {'-' * 25}-+-{'-' * 12}-+-{'-' * 18}-+-{'-' * 12}")
        for level in ["weak", "medium", "strong"]:
            if level not in results:
                continue
            answer, metrics, elapsed, cost = results[level]
            name = MODELS[level]["name"]
            in_t = metrics.get("prompt_tokens", 0)
            out_t = metrics.get("completion_tokens", 0)
            print(f"  {name:<25} | {format_time(elapsed):<12} | {in_t} / {out_t:<16} | {format_cost(cost)}")

    # --- Финальное сравнение ---
    if args.compare and len(results) >= 2:
        print(f"\n{'=' * 60}")
        print("  📊 Итоговое сравнение")
        print(f"{'=' * 60}")
        comparison = run_comparison(query, results, max_tokens=1024)
        print(f"\nБот: {comparison}")

    print(f"\n{'=' * 60}")
    print("  ✅ Сравнение завершено.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()