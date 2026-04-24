"""Memory tier tests — core/recall/archival.

Archival needs the embedder → requires Ollama bge-m3 running. Skip if unreachable.
"""

from __future__ import annotations

import httpx
import pytest

from oracle.config import settings
from oracle.memory.core import CoreMemory
from oracle.memory.recall import RecallMemory


def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.oracle_ollama_host}/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def test_core_memory_defaults_and_edit(oracle_home):
    cm = CoreMemory()
    text = cm.read()
    assert "# user" in text
    assert len(text) > 20

    cm.append("- test: hello")
    assert "test: hello" in cm.read()

    cm.write("# minimal\njust this.\n")
    assert cm.read().strip() == "# minimal\njust this."


def test_recall_log_and_search(oracle_home):
    rm = RecallMemory()
    assert rm.count() == 0

    rm.log(role="user", content="what time is it", thread_id="t1")
    rm.log(role="assistant", content="about half past four", thread_id="t1")
    rm.log(role="user", content="set a reminder for dinner", thread_id="t2")

    assert rm.count() == 3
    recent = rm.recent(5)
    assert len(recent) == 3
    assert recent[0]["content"] == "set a reminder for dinner"

    t1 = rm.recent(5, thread_id="t1")
    assert len(t1) == 2

    hits = rm.search("dinner")
    assert any("dinner" in h["content"] for h in hits)


@pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable")
def test_archival_store_and_query(oracle_home):
    from oracle.memory.archival import ArchivalMemory

    am = ArchivalMemory()
    assert am.count() == 0

    am.store("My favorite programming language is Python.", tags=["pref"])
    am.store("My primary workstation uses an RTX 4090.", tags=["hardware"])
    am.store("I prefer reading on Kindle over paper.", tags=["pref"])

    assert am.count() == 3

    hits = am.query("what GPU do I have", k=2)
    assert hits
    assert any("4090" in h["content"] for h in hits)
