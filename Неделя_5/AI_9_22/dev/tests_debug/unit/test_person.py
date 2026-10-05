# -*- coding: utf-8 -*-
"""Юнит-тесты персонализации: мультипрофиль, миграция, роутер, активный профиль."""
import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from storage.db import ProfileRepository
from storage.store import Store
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent
from core.profile_router import ProfileRouter


def make_store(tmp_path):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    return Store(str(tmp_path / "users"), profile_repo=repo)


def make_agent(tmp_path):
    store = make_store(tmp_path)
    memory = MemoryManager(default_layers(store))
    return Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store, user_id="u")


CHEMIST = {"id": "u", "name": "Химик", "domain": "химия",
           "triggers": ["химия", "реактив", "реакция"],
           "style": {"answers": "строго по формулам"}, "constraints": {}, "context": {},
           "skills": [{"name": "spec", "instructions": "составь спеку ответа"},
                      {"name": "review", "instructions": "проверь факты по домену"}]}
ECONOMIST = {"id": "u", "name": "Экономист", "domain": "экономика",
             "triggers": ["бюджет", "цена"],
             "style": {"answers": "считай выгоду"}, "constraints": {}, "context": {}}


def test_multi_profile_roundtrip(tmp_path):
    """Два профиля сохраняются/читаются независимо; list_profiles возвращает оба."""
    store = make_store(tmp_path)
    store.save_profile("u", CHEMIST, "chemist")
    store.save_profile("u", ECONOMIST, "economist")
    assert store.load_profile("u", "chemist")["name"] == "Химик"
    assert store.load_profile("u", "economist")["name"] == "Экономист"
    profiles = store.list_profiles("u")
    assert [pid for pid, _ in profiles] == ["chemist", "economist"]
    # Первый профиль автоматически default; get/set_default работают.
    assert store.profile_repo.get_default("u") == "chemist"
    assert store.set_default_profile("u", "economist")
    assert store.profile_repo.get_default("u") == "economist"
    assert not store.set_default_profile("u", "nope")
    # Зеркала профилей — отдельные файлы.
    assert (tmp_path / "users" / "u" / "profiles" / "chemist.json").is_file()
    assert (tmp_path / "users" / "u" / "profiles" / "economist.json").is_file()


def test_migration_old_schema(tmp_path):
    """БД старой схемы (один профиль) после открытия даёт профиль default."""
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE profiles (user_id TEXT PRIMARY KEY, "
                 "profile_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
    conn.execute("INSERT INTO profiles VALUES ('legacy', ?, '2026-01-01 00:00:00')",
                 (json.dumps({"id": "legacy", "name": "Старый",
                              "style": {"answers": "s"}}, ensure_ascii=False),))
    conn.commit()
    conn.close()
    repo = ProfileRepository(db_path)
    profile = repo.load_profile("legacy")
    # Данные не потеряны, профиль стал default.
    assert profile["name"] == "Старый"
    assert profile["profile_id"] == "default"
    assert repo.get_default("legacy") == "default"
    assert repo.list_profiles("legacy") == [("default", True)]
    # exists() семантику не изменил: есть хотя бы один профиль.
    assert repo.exists("legacy")
    assert not repo.exists("unknown")


def test_backward_compatibility(tmp_path):
    """load_profile без id = дефолтный; MemoryContext с 3 аргументами работает."""
    store = make_store(tmp_path)
    store.save_profile("u", {"id": "u", "name": "База", "style": {}, "constraints": {},
                             "context": {}})
    store.save_profile("u", ECONOMIST, "economist")
    # Без profile_id → дефолтный профиль (как в дне 11).
    assert store.load_profile("u")["name"] == "База"
    # Зеркало default — старое profile.json (обратная совместимость).
    assert (tmp_path / "users" / "u" / "profile.json").is_file()
    # MemoryContext с тремя аргументами — profile_id пустой, as_dict включает его.
    ctx = MemoryContext("u", "t", "s")
    assert ctx.profile_id == ""
    assert ctx.as_dict()["profile_id"] == ""
    # Слой Profile читает дефолтный профиль через 3-аргументный контекст.
    memory = MemoryManager(default_layers(store))
    assert memory.layers["profile"].read(ctx)["name"] == "База"


def test_router_triggers_and_none(tmp_path):
    """Роутер: триггеры выбирают профиль; нет совпадений → None; explain — разбор."""
    store = make_store(tmp_path)
    store.save_profile("u", CHEMIST, "chemist")
    store.save_profile("u", ECONOMIST, "economist")
    logs = []
    router = ProfileRouter(store, log=logs.append)
    assert router.route("u", "Какая РЕАКЦИЯ идёт?") == "chemist"   # регистронезависимо
    assert router.route("u", "посчитай бюджет") == "economist"
    assert router.route("u", "привет") is None                     # ноль → None
    explanation = router.explain("u", "бюджет")
    assert "счёт" in explanation and "economist" in explanation
    assert any("[Роутер]" in line for line in logs)


def test_router_tie_returns_none(tmp_path):
    """Ничья (равные максимумы) → None: остаёмся на текущем/дефолтном."""
    store = make_store(tmp_path)
    store.save_profile("u", CHEMIST, "chemist")
    store.save_profile("u", {"id": "u", "name": "Химик2", "domain": "химия",
                             "triggers": ["химия"]}, "chem2")
    router = ProfileRouter(store)
    # «химия»: chemist = 2 (триггер) + 1 (домен) = 3; chem2 = 2 + 1 = 3 → ничья.
    assert router.route("u", "химия") is None


def test_profile_block_differs(tmp_path):
    """Блок profile: имя активного профиля + пайплайн скиллов; два профиля → разные блоки."""
    store = make_store(tmp_path)
    store.save_profile("u", CHEMIST, "chemist")
    store.save_profile("u", ECONOMIST, "economist")
    memory = MemoryManager(default_layers(store))
    block_chem = memory.layers["profile"].as_prompt_block(
        MemoryContext("u", profile_id="chemist"))
    block_eco = memory.layers["profile"].as_prompt_block(
        MemoryContext("u", profile_id="economist"))
    assert block_chem.splitlines()[0] == "Профиль: Химик (chemist)"
    assert "Пайплайн скиллов:" in block_chem
    assert "1. spec: составь спеку ответа" in block_chem
    assert "2. review: проверь факты по домену" in block_chem
    assert "Домен: химия" in block_chem
    # Прежние строки сохранены (обратная совместимость блока).
    assert "Имя: Химик" in block_chem
    # ДВА разных профиля на один запрос → РАЗНЫЕ блоки.
    assert block_chem != block_eco
    assert block_eco.splitlines()[0] == "Профиль: Экономист (economist)"


def test_agent_switch_profile(tmp_path):
    """switch_profile меняет активный профиль; несуществующий → False."""
    agent = make_agent(tmp_path)
    agent.initialize_user("u", "Ю", {"style": "a", "constraints": "b", "context": "c"})
    agent.store.save_profile("u", CHEMIST, "chemist")
    assert agent.active_profile is None
    assert agent.switch_profile("chemist")
    assert agent.active_profile == "chemist"
    assert not agent.switch_profile("nope")
    assert agent.active_profile == "chemist"
    # Активный профиль попадает в контекст промта.
    pctx = agent.build_context("вопрос")
    assert "Химик" in pctx.memory_blocks.get("profile", "")


def test_agent_auto_route_switches_before_prompt(tmp_path):
    """auto_route переключает профиль по запросу ДО сборки промта."""
    agent = make_agent(tmp_path)
    agent.initialize_user("u", "Ю", {"style": "a", "constraints": "b", "context": "c"})
    agent.store.save_profile("u", ECONOMIST, "economist")
    agent.auto_route = True
    answer = agent.respond("посчитай бюджет покупки")
    assert agent.active_profile == "economist"
    # Ответ MockClient отражает блоки: в промт попал профиль Экономист.
    assert "Экономист" in answer
    # Запрос без совпадений — профиль не меняется.
    agent.respond("привет")
    assert agent.active_profile == "economist"


def test_two_profiles_different_answers(tmp_path):
    """Один запрос — разные ответы для разных профилей (MockClient отражает блоки)."""
    agent = make_agent(tmp_path)
    agent.initialize_user("u", "Ю", {"style": "a", "constraints": "b", "context": "c"})
    agent.store.save_profile("u", CHEMIST, "chemist")
    agent.store.save_profile("u", ECONOMIST, "economist")
    agent.switch_profile("chemist")
    answer_chem = agent.respond("расскажи про это")
    agent.switch_profile("economist")
    answer_eco = agent.respond("расскажи про это")
    assert "Химик" in answer_chem and "Экономист" in answer_eco
    assert answer_chem != answer_eco
