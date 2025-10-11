from __future__ import annotations

import json
from app.core.llm.extractor import EventDraft, extract_event_fields
from app.core.llm.is_event_classifier import ClassifierOut, classify
from app.core.llm import summarizer


def test_extractor_validation(monkeypatch):
    payload = json.dumps({
        "title": "Концерт симфонической музыки",
        "date_iso": "2025-01-10",
        "time_24h": "19:00",
        "venue_name": "Зал имени Листова",
        "address": "Севастополь, Ленина 1",
        "price_min": 500,
        "price_max": 1500,
        "category": "concert",
        "source_url": "https://example.com/event/1"
    })

    from app.core.llm import client as llm_client
    monkeypatch.setattr(llm_client, "chat_complete", lambda **kwargs: payload)

    draft = extract_event_fields("raw text", None)
    assert isinstance(draft, EventDraft)
    assert draft.title and draft.category == "concert"
    assert draft.date_iso == "2025-01-10"
    assert draft.time_24h == "19:00"


def test_classifier(monkeypatch):
    payload = json.dumps({"is_event": True, "reasons": ["Есть дата", "Есть место"]})
    from app.core.llm import client as llm_client
    monkeypatch.setattr(llm_client, "chat_complete", lambda **kwargs: payload)
    out = classify("Встречаемся 10 января в 19:00 в театре")
    assert isinstance(out, ClassifierOut)
    assert out.is_event is True
    assert len(out.reasons) >= 1


def test_summarizer(monkeypatch):
    payload = "Короткое описание события. Указаны место и время."
    from app.core.llm import client as llm_client
    monkeypatch.setattr(llm_client, "chat_complete", lambda **kwargs: payload)
    s = summarizer.summarize("Большой текст ...")
    assert isinstance(s, str)
    assert 10 <= len(s) <= 200
