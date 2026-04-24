"""Pytest fixtures — redirect Oracle data into a tmp path per test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def oracle_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "oracle-home"
    home.mkdir()
    monkeypatch.setenv("ORACLE_HOME", str(home))
    import importlib
    from oracle import config as cfg_mod

    importlib.reload(cfg_mod)
    # Memory/retrieval modules bind `settings` at import time — reload them
    # so their default paths resolve against the tmp ORACLE_HOME.
    from oracle.memory import archival, core, embeddings, recall, tiers
    from oracle.retrieval import index as retrieval_index
    from oracle.retrieval import ingest as retrieval_ingest

    for m in (
        core, recall, archival, embeddings, tiers,
        retrieval_index, retrieval_ingest,
    ):
        importlib.reload(m)
    return home
