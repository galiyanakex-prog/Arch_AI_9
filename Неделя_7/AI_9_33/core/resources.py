# -*- coding: utf-8 -*-
"""Снятие ресурсов хоста во время прогона (Ревизия 8, этап 8, часть 4).

Модуль уровня хоста: парсит вывод `ps`/`free`/`lms ps` и умеет периодически
сэмплировать потребление процесса LM Studio (llama-server) в фоне. Никакой
бизнес-логики агента и никаких импортов из `rag/` (граница §5).

Дискретного GPU на хосте нет → inference по CPU; VRAM неприменим (см. отчёт).
"""
import re
import subprocess
import threading


def parse_ps(text: str) -> dict:
    """Разбор `ps -o rss=,pcpu= -p <pid>` → {"rss_kb", "pcpu"}.

    Пустой/некорректный вывод → нули (процесс мог завершиться).
    """
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                return {"rss_kb": int(float(parts[0])), "pcpu": float(parts[1])}
            except ValueError:
                continue
    return {"rss_kb": 0, "pcpu": 0.0}


def parse_free(text: str) -> dict:
    """Разбор `free -m` → {"total_mb", "used_mb", "available_mb"} (строка Mem:)."""
    for line in (text or "").splitlines():
        if line.strip().startswith("Mem:"):
            parts = line.split()
            try:
                return {"total_mb": int(parts[1]), "used_mb": int(parts[2]),
                        "available_mb": int(parts[6]) if len(parts) > 6 else int(parts[3])}
            except (ValueError, IndexError):
                break
    return {"total_mb": 0, "used_mb": 0, "available_mb": 0}


def parse_lms_ps(text: str) -> list:
    """Разбор `lms ps` → список {"identifier", "status", "size", "context"}.

    Формат строки: IDENTIFIER MODEL STATUS SIZE_NUM SIZE_UNIT CONTEXT PARALLEL …
    (MODEL повторяет identifier; SIZE — «2.54 GB» двумя токенами).
    """
    out = []
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] == "IDENTIFIER":
            continue
        size = ""
        context = ""
        # SIZE — число + единица (GB/MB/KB); CONTEXT — целое после них.
        for idx in range(3, len(parts) - 1):
            if re.fullmatch(r"\d+(\.\d+)?", parts[idx]) and \
                    parts[idx + 1] in ("GB", "MB", "KB"):
                size = f"{parts[idx]} {parts[idx + 1]}"
                if idx + 2 < len(parts) and parts[idx + 2].isdigit():
                    context = parts[idx + 2]
                break
        out.append({"identifier": parts[0], "status": parts[2],
                    "size": size, "context": context})
    return out


def _run(cmd: list, timeout: float = 10.0) -> str:
    """Запуск команды; ошибки/таймаут → пустая строка (сэмпл пропускается)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def find_lmstudio_pid() -> int:
    """PID процесса llama-server (LM Studio backend); 0, если не найден."""
    out = _run(["pgrep", "-f", "llama-server"])
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


class ResourceSampler:
    """Периодический сэмплер ресурсов процесса LM Studio + памяти хоста.

    `runner` — инъекция для тестов: callable(cmd)->str (по умолчанию `_run`).
    `pid` — PID llama-server; 0/None → ищем автоматически при старте.
    """

    def __init__(self, pid: int = None, interval: float = 5.0, runner=None,
                 model_hint: str = ""):
        self.pid = pid or 0
        self.interval = interval
        self.runner = runner or _run
        self.model_hint = model_hint
        self.samples = []          # список {"rss_kb", "pcpu"}
        self.free_before = {}
        self.free_after = {}
        self.lms = []
        self._thread = None
        self._stop = threading.Event()

    def _resolve_pid(self) -> int:
        """PID активного llama-server (LM Studio перезапускает его при смене модели).

        `pgrep -f llama-server` может вернуть несколько PID (старые/зомби-процессы
        с крошечным RSS). Берём процесс с максимальным RSS — это и есть активный
        inference-бэкенд.
        """
        out = self.runner(["pgrep", "-f", "llama-server"])
        pids = [int(line.strip()) for line in (out or "").splitlines()
                if line.strip().isdigit()]
        if not pids:
            return 0
        best_pid, best_rss = 0, -1
        for pid in pids:
            text = self.runner(["ps", "-o", "rss=", "-p", str(pid)])
            rss = 0
            for line in (text or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    rss = int(line)
                    break
            if rss > best_rss:
                best_pid, best_rss = pid, rss
        return best_pid

    def _sample_once(self):
        # PID переопределяем каждый раз: LM Studio поднимает новый llama-server
        # под каждую модель (JIT), старый PID становится недействительным.
        pid = self._resolve_pid() or self.pid
        if not pid:
            return
        self.pid = pid
        text = self.runner(["ps", "-o", "rss=,pcpu=", "-p", str(pid)])
        self.samples.append(parse_ps(text))

    def _loop(self):
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self.interval)

    def start(self):
        """Снять «до», найти PID, запустить фоновый поток сэмплирования."""
        self.free_before = parse_free(self.runner(["free", "-m"]))
        if not self.pid:
            self.pid = self._resolve_pid()
        self._sample_once()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        """Остановить поток, снять «после» и `lms ps` (модель уже загружена)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 2)
        self._sample_once()
        self.free_after = parse_free(self.runner(["free", "-m"]))
        self.lms = parse_lms_ps(self.runner(["lms", "ps"]))
        return self

    def summary(self) -> dict:
        """Агрегат: пик/среднее RSS, средний CPU, память до/после, размер модели."""
        rss = [s["rss_kb"] for s in self.samples if s["rss_kb"]]
        cpu = [s["pcpu"] for s in self.samples]
        model_size = ""
        if self.lms:
            # Выбираем строку нужной модели (по подсказке), иначе первую.
            chosen = self.lms[0]
            if self.model_hint:
                for row in self.lms:
                    if self.model_hint.lower() in row["identifier"].lower():
                        chosen = row
                        break
            model_size = chosen["size"]
        return {
            "pid": self.pid,
            "samples": len(self.samples),
            "rss_peak_mb": round(max(rss) / 1024, 1) if rss else 0.0,
            "rss_avg_mb": round(sum(rss) / len(rss) / 1024, 1) if rss else 0.0,
            "cpu_avg": round(sum(cpu) / len(cpu), 1) if cpu else 0.0,
            "free_before": self.free_before,
            "free_after": self.free_after,
            "model_size": model_size,
        }


def render_resources_section(resources: dict) -> str:
    """Markdown-раздел «Ресурсы» для отчёта «до/после» (этап 8)."""
    if not resources:
        return ""
    before = resources.get("free_before", {})
    after = resources.get("free_after", {})
    lines = [
        "## Ресурсы (хост)",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| PID llama-server | {resources.get('pid', 0)} |",
        f"| Сэмплов | {resources.get('samples', 0)} |",
        f"| RSS пик, МБ | {resources.get('rss_peak_mb', 0)} |",
        f"| RSS среднее, МБ | {resources.get('rss_avg_mb', 0)} |",
        f"| CPU среднее, % | {resources.get('cpu_avg', 0)} |",
        f"| Размер загруженной модели | {resources.get('model_size', '—') or '—'} |",
        f"| RAM до (used/available, МБ) | {before.get('used_mb', 0)} / "
        f"{before.get('available_mb', 0)} |",
        f"| RAM после (used/available, МБ) | {after.get('used_mb', 0)} / "
        f"{after.get('available_mb', 0)} |",
        "",
        "**GPU:** дискретного GPU нет, inference по CPU, VRAM неприменим.",
        "",
    ]
    return "\n".join(lines)
