"""Handoff decisions use evidence confidence and configurable bilingual phrases."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.mongodb import MongoDB
from app.models.schemas import HandoffConfig
from app.providers.database import MockDatabaseProvider
from app.providers.database.mongodb_provider import MongoDBProvider
from app.routes.chat import check_handoff_suggestion
from app.services.rag_engine import RAGEngine


@pytest.fixture
def handoff_db(monkeypatch):
    database = MagicMock()
    database.get_site_handoff_config = AsyncMock(return_value={"enabled": True, "confidence_threshold": 0.3})
    monkeypatch.setattr("app.routes.chat.get_mongodb", AsyncMock(return_value=database))
    return database


async def test_no_evidence_triggers_handoff_with_legacy_english_configuration(handoff_db):
    handoff_db.get_site_handoff_config.return_value = {
        "enabled": True, "confidence_threshold": 0.3,
        "auto_suggest_phrases": ["I'm not sure", "I don't have information", "I cannot help with", "please contact support"],
    }
    engine = RAGEngine.__new__(RAGEngine)
    confidence = engine._calculate_confidence([])

    assert await check_handoff_suggestion("site", "Hiện mình chưa có đủ thông tin để trả lời.", confidence) == (True, "low_confidence")


@pytest.mark.parametrize("answer", [
    "Tôi chưa có đủ thông tin để trả lời.",
    "Mình chưa đủ thông tin về chính sách này.",
    "Tôi không có đủ thông tin để xác nhận.",
    "Mình không tìm thấy thông tin về mẫu này.",
    "Tôi chưa có thông tin về giá mới.",
    "Tôi không chắc về thông tin này.",
    "Mình không chắc thông tin này có chính xác không.",
    "TÔI CHƯA CÓ ĐỦ\n   THÔNG TIN để trả lời.",
    "I'm not sure about that.",
])
async def test_default_phrases_detect_uncertainty_even_with_high_retrieval_confidence(handoff_db, answer):
    assert await check_handoff_suggestion("site", answer, 0.8) == (True, "uncertain_response")


@pytest.mark.parametrize("confidence,threshold,expected", [(0.59, 0.6, True), (0.6, 0.6, False), (0.61, 0.6, False), (0.0, 0.3, True), (0.0, 0.0, False)])
async def test_configured_threshold_keeps_strict_below_semantics(handoff_db, confidence, threshold, expected):
    handoff_db.get_site_handoff_config.return_value = {"enabled": True, "confidence_threshold": threshold, "auto_suggest_phrases": []}
    assert await check_handoff_suggestion("site", "C114 được bảo hành hai năm.", confidence) == (expected, "low_confidence" if expected else None)


@pytest.mark.parametrize("phrases,answer,expected", [
    ([], "Tôi chưa đủ thông tin để trả lời.", False),
    (["hết hàng"], "Sản phẩm đã HẾT\n HÀNG.", True),
    (["hết hàng"], "Tôi chưa đủ thông tin để trả lời.", False),
    (["", "   "], "C114 được bảo hành hai năm.", False),
])
async def test_custom_phrases_are_respected_and_blank_entries_do_not_match(handoff_db, phrases, answer, expected):
    config = {"enabled": True, "auto_suggest_phrases": list(phrases)}
    handoff_db.get_site_handoff_config.return_value = config
    assert await check_handoff_suggestion("site", answer, 0.8) == (expected, "uncertain_response" if expected else None)
    assert config["auto_suggest_phrases"] == phrases


@pytest.mark.parametrize("config", [None, {"enabled": False}])
async def test_disabled_or_missing_handoff_config_never_suggests(handoff_db, config):
    handoff_db.get_site_handoff_config.return_value = config
    assert await check_handoff_suggestion("site", "Tôi chưa đủ thông tin.", 0.0) == (False, None)


async def test_successful_vietnamese_answer_does_not_trigger_phrase_handoff(handoff_db):
    assert await check_handoff_suggestion("site", "Khóa C114 không cần kết nối mạng; bảo hành hai năm.", 0.8) == (False, None)


@pytest.mark.parametrize("implementation", ["schema", "legacy", "provider", "mock"])
async def test_all_configuration_defaults_recognize_vietnamese(handoff_db, implementation):
    if implementation == "schema":
        config = HandoffConfig().model_dump()
    elif implementation == "mock":
        database = MockDatabaseProvider()
        database.seed_site({"site_id": "site", "url": "https://example.test"})
        config = await database.get_site_handoff_config("site")
    else:
        database = MongoDB() if implementation == "legacy" else MongoDBProvider()
        database.db = MagicMock()
        database.db.sites.find_one = AsyncMock(return_value={"site_id": "site"})
        config = await database.get_site_handoff_config("site")
    handoff_db.get_site_handoff_config.return_value = config
    assert await check_handoff_suggestion("site", "Tôi chưa có đủ thông tin để trả lời.", 0.8) == (True, "uncertain_response")
