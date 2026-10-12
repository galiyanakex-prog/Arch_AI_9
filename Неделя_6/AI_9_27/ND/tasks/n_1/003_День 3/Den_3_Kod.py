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


def run_direct(user_query: str, temperature: float = 0.7,
               max_tokens: int = 500) -> str:
    """Прямой ответ без дополнительных инструкций."""
    messages = [
        {
            "role": "system",
            "content": "Ты полезный ассистент. Отвечай на русском языке.",
        },
        {"role": "user", "content": user_query},
    ]
    return send_request(messages, max_tokens=max_tokens, temperature=temperature)


def run_step_by_step(user_query: str, temperature: float = 0.7,
                     max_tokens: int = 500) -> str:
    """Пошаговое решение (chain-of-thought)."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты полезный ассистент. Отвечай на русском языке. "
                "Решай задачу пошагово, подробно объясняя каждый шаг рассуждений."
            ),
        },
        {"role": "user", "content": user_query},
    ]
    return send_request(messages, max_tokens=max_tokens, temperature=temperature)


def run_generate_prompt(user_query: str, temperature: float = 0.7,
                        max_tokens: int = 500) -> tuple[str, str]:
    """Сначала модель составляет промпт, затем использует его для решения."""
    # Шаг 1: генерируем промпт
    messages_gen = [
        {
            "role": "system",
            "content": (
                "Ты полезный ассистент. Отвечай на русском языке. "
                "Составь оптимальный промпт для решения следующей задачи. "
                "Верни ТОЛЬКО текст промпта, без пояснений."
            ),
        },
        {"role": "user", "content": user_query},
    ]
    generated_prompt = send_request(messages_gen, max_tokens=max_tokens,
                                    temperature=temperature)

    # Шаг 2: используем сгенерированный промпт
    messages_solve = [
        {
            "role": "system",
            "content": "Ты полезный ассистент. Отвечай на русском языке.",
        },
        {"role": "user", "content": generated_prompt},
    ]
    answer = send_request(messages_solve, max_tokens=max_tokens,
                          temperature=temperature)
    return generated_prompt, answer


def run_experts(user_query: str, temperature: float = 0.7,
                max_tokens: int = 500) -> str:
    """Группа экспертов: аналитик, инженер, критик — каждый даёт решение."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты полезный ассистент. Отвечай на русском языке. "
                "Представь группу экспертов: аналитик, инженер, критик. "
                "Каждый эксперт даёт своё решение задачи. "
                "Оформи ответ в виде трёх блоков, каждый с заголовком роли."
            ),
        },
        {"role": "user", "content": user_query},
    ]
    return send_request(messages, max_tokens=max_tokens, temperature=temperature)


def run_comparison(user_query: str, direct_answer: str,
                   step_by_step_answer: str, generated_prompt: str,
                   generated_prompt_answer: str, experts_answer: str,
                   expected_answer: str | None = None,
                   temperature: float = 0.2, max_tokens: int = 1024) -> str:
    """Финальное сравнение четырёх способов рассуждения.
    
    Использует подход LLM-as-a-Judge: модель оценивает все ответы по критериям.
    Если передан expected_answer, сверяет результаты с эталоном.
    """
    comparison_prompt = (
        "Ты независимый эксперт по оценке качества решений. "
        "Сравни четыре решения одной и той же задачи, полученных разными способами. "
        "Оцени каждый способ и определи лучший.\n\n"
        "Критерии оценки:\n"
        "1. Точность и логическая корректность результата\n"
        "2. Полнота и обоснованность рассуждений\n"
        "3. Чёткость структуры и пошаговость объяснения\n"
        "4. Способность проверить правильность ответа\n\n"
    )
    
    if expected_answer:
        comparison_prompt += (
            f"Эталонный ответ: {expected_answer}\n"
            "Сверь каждый результат с эталоном.\n\n"
        )
    
    comparison_prompt += (
        f"Задача: {user_query}\n\n"
        f"1. Прямой ответ:\n{direct_answer}\n\n"
        f"2. Пошаговое решение:\n{step_by_step_answer}\n\n"
        f"3. Решение по сгенерированному промпту:\n{generated_prompt_answer}\n\n"
        f"4. Группа экспертов:\n{experts_answer}\n\n"
        "Для каждого способа кратко оцени по критериям выше.\n"
        "Затем назови наиболее точный и убедительный способ.\n"
        "Объясни, почему он лучше остальных.\n"
        "Не оценивай длину текста как признак точности."
    )
    
    messages = [
        {
            "role": "system",
            "content": "Ты независимый эксперт по оценке качества решений. Отвечай на русском языке.",
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


def print_and_return_tuple(label: str, generated_prompt: str, answer: str) -> tuple[str, str]:
    """Выводит заголовок и содержимое для генерации промпта, возвращает кортеж."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"📝 Составленный промпт: {generated_prompt}")
    print(f"\nБот: {answer}")
    return generated_prompt, answer


# ---------------------------------------------------------------------------
# Интерактивный режим
# ---------------------------------------------------------------------------
def run_interactive(temperature: float = 0.7, max_tokens: int = 500,
                    expected_answer: str | None = None) -> None:
    """Запускает интерактивный режим с вводом пользователя."""
    print("🤖 Сравнение способов рассуждения")
    print("Введите «выход» для завершения.\n")

    while True:
        user_input = input("Вы: ").strip()

        if user_input.lower() == "выход":
            print("До свидания!")
            break

        if not user_input:
            continue

        # --- Прямой ответ ---
        direct_answer = print_and_return(
            "=== Прямой ответ (без инструкций) ===",
            run_direct(user_input, temperature=temperature, max_tokens=max_tokens)
        )

        # --- Пошаговое решение ---
        step_by_step_answer = print_and_return(
            "=== Пошаговое решение (chain-of-thought) ===",
            run_step_by_step(user_input, temperature=temperature, max_tokens=max_tokens)
        )

        # --- Генерация промпта ---
        gen_prompt, gen_answer = run_generate_prompt(
            user_input, temperature=temperature, max_tokens=max_tokens
        )
        print_and_return_tuple("=== Генерация промпта ===", gen_prompt, gen_answer)

        # --- Группа экспертов ---
        experts_answer = print_and_return(
            "=== Группа экспертов ===",
            run_experts(user_input, temperature=temperature, max_tokens=max_tokens)
        )

        # --- Финальное сравнение ---
        print(f"\n{'=' * 60}")
        print("  📊 Итоговое сравнение")
        print(f"{'=' * 60}")
        comparison = run_comparison(
            user_input, direct_answer, step_by_step_answer,
            gen_prompt, gen_answer, experts_answer,
            expected_answer, temperature=temperature, max_tokens=max_tokens
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
        description="Сравнение способов рассуждения LLM через RouterAI API"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Текст запроса к модели (без флагов — интерактивный режим)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Прямой ответ — без дополнительных инструкций",
    )
    parser.add_argument(
        "--step-by-step",
        action="store_true",
        dest="step_by_step",
        help="Пошаговое решение — модель рассуждает цепочкой (chain-of-thought)",
    )
    parser.add_argument(
        "--generate-prompt",
        action="store_true",
        help="Сначала модель составляет промпт, затем решает задачу",
    )
    parser.add_argument(
        "--experts",
        action="store_true",
        help="Группа экспертов — аналитик, инженер, критик дают решение",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Запустить все четыре способа для сравнения",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Запустить финальное сравнение всех способов",
    )
    parser.add_argument(
        "--expected-answer",
        type=str,
        default=None,
        metavar="TEXT",
        help="Эталонный ответ для сверки (необязательно)",
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
        run_interactive(temperature=args.temperature, max_tokens=args.max_tokens,
                        expected_answer=args.expected_answer)
        return

    query = args.query

    # Если указан --all — запускаем все четыре способа + сравнение
    if args.all:
        args.direct = True
        args.step_by_step = True
        args.generate_prompt = True
        args.experts = True
        args.compare = True
    # Если ни один способ не указан — запускаем все четыре + сравнение
    elif not args.direct and not args.step_by_step and not args.generate_prompt and not args.experts:
        args.direct = True
        args.step_by_step = True
        args.generate_prompt = True
        args.experts = True
        args.compare = True

    # --- Прямой ответ ---
    direct_answer = ""
    if args.direct:
        direct_answer = print_and_return(
            "=== Прямой ответ (без инструкций) ===",
            run_direct(query, temperature=args.temperature, max_tokens=args.max_tokens)
        )

    # --- Пошаговое решение ---
    step_by_step_answer = ""
    if args.step_by_step:
        step_by_step_answer = print_and_return(
            "=== Пошаговое решение (chain-of-thought) ===",
            run_step_by_step(query, temperature=args.temperature, max_tokens=args.max_tokens)
        )

    # --- Генерация промпта ---
    gen_prompt = ""
    gen_answer = ""
    if args.generate_prompt:
        gen_prompt, gen_answer = run_generate_prompt(
            query, temperature=args.temperature, max_tokens=args.max_tokens
        )
        print_and_return_tuple("=== Генерация промпта ===", gen_prompt, gen_answer)

    # --- Группа экспертов ---
    experts_answer = ""
    if args.experts:
        experts_answer = print_and_return(
            "=== Группа экспертов ===",
            run_experts(query, temperature=args.temperature, max_tokens=args.max_tokens)
        )

    # --- Финальное сравнение ---
    if args.compare:
        print(f"\n{'=' * 60}")
        print("  📊 Итоговое сравнение")
        print(f"{'=' * 60}")
        comparison = run_comparison(
            query, direct_answer, step_by_step_answer,
            gen_prompt, gen_answer, experts_answer,
            args.expected_answer, temperature=args.temperature, max_tokens=args.max_tokens
        )
        print(f"\nБот: {comparison}")

    print(f"\n{'=' * 60}")
    print("  ✅ Сравнение завершено.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()