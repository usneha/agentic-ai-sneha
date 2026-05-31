import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Each test gets a fresh in-memory DB at a temp path."""
    monkeypatch.setenv("LEARNING_DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import database
    importlib.reload(database)
    database.init_db()
    return database


def test_profile_default(db):
    profile = db.get_profile()
    assert profile is None


def test_save_and_get_profile(db):
    db.save_profile("I am a data scientist", ["Use analogies", "Show the math"], "standard")
    profile = db.get_profile()
    assert profile["background"] == "I am a data scientist"
    assert "Use analogies" in profile["explanation_styles"]
    assert profile["detail_level"] == "standard"


def test_create_and_get_topic(db):
    topic_id = db.create_topic("Transformer Architecture")
    topics = db.get_all_topics()
    assert len(topics) == 1
    assert topics[0]["name"] == "Transformer Architecture"
    assert topics[0]["id"] == topic_id


def test_add_sources_to_topic(db):
    topic_id = db.create_topic("Causal Inference")
    db.add_sources(topic_id, [{"name": "notes.txt", "type": "TXT", "content": "some text"}])
    topic = db.get_topic(topic_id)
    assert len(topic["sources"]) == 1
    assert topic["sources"][0]["name"] == "notes.txt"


def test_save_journal(db):
    topic_id = db.create_topic("Bayesian Methods")
    journal = {"summary": "s", "journal": "j", "concepts": ["c1"], "resources": []}
    db.save_journal(topic_id, journal)
    topic = db.get_topic(topic_id)
    assert topic["journal"]["summary"] == "s"


def test_delete_topic(db):
    topic_id = db.create_topic("To Delete")
    db.delete_topic(topic_id)
    assert db.get_topic(topic_id) is None
