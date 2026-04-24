"""Mesh identity + sync tests — fully offline (no Ollama required)."""

from __future__ import annotations

import json

import pytest


def test_keygen_and_sign_verify_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    # Reload config so ORACLE_HOME takes effect
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    # Reload mesh modules that bound settings at import time
    from nexus.mesh import identity as ident_mod
    importlib.reload(ident_mod)

    ident = ident_mod.new_identity(label="test-node")
    assert ident.pubkey_b64
    assert ident.privkey_b64

    data = b"hello world"
    sig = ident_mod.sign(data, identity=ident)
    assert ident_mod.verify(data, signature_b64=sig, pubkey_b64=ident.pubkey_b64)
    assert not ident_mod.verify(b"tampered", signature_b64=sig, pubkey_b64=ident.pubkey_b64)


def test_bundle_verification_rejects_untrusted_producer(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus.mesh import identity as ident_mod
    from nexus.mesh import sync as sync_mod
    importlib.reload(ident_mod)
    importlib.reload(sync_mod)

    ident = ident_mod.new_identity(label="producer")
    bundle = sync_mod.SkillBundle(
        bundle_id="b1",
        producer=ident.pubkey_b64,
        produced_ts=0.0,
        skills=[],
    )
    bundle.signature = ident_mod.sign(bundle.canonical_payload(), identity=ident)

    report = sync_mod.install_bundle(bundle)
    assert not report["ok"]
    assert any("not in allowlist" in str(r) for r in report["rejected"][0].values())


def test_bundle_with_trusted_producer_installs(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus.mesh import identity as ident_mod
    from nexus.mesh import sync as sync_mod
    importlib.reload(ident_mod)
    importlib.reload(sync_mod)

    ident = ident_mod.new_identity(label="producer")
    ident_mod.add_peer(pubkey_b64=ident.pubkey_b64, label="producer", url="http://x")

    code = '''\
from nexus.skills.base import Skill, SkillContext


class MeshEcho(Skill):
    id = "mesh_echo_test"
    name = "Mesh Echo"
    description = "Echo input back."
    tags = ["test"]
    inputs = {"text": "str"}
    outputs = {"echo": "str"}
    origin = "self_written"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        return {"echo": inputs.get("text", "")}
'''
    import hashlib
    file_hash = "sha256:" + hashlib.sha256(code.encode()).hexdigest()
    ms = sync_mod.MeshSkill(id="mesh_echo_test", file_hash=file_hash, code=code)
    bundle = sync_mod.SkillBundle(
        bundle_id="b1",
        producer=ident.pubkey_b64,
        produced_ts=0.0,
        skills=[ms],
    )
    bundle.signature = ident_mod.sign(bundle.canonical_payload(), identity=ident)

    report = sync_mod.install_bundle(bundle)
    assert report["ok"], report
    assert "mesh_echo_test" in report["installed"]

    installed = sync_mod.MESH_SKILLS_DIR / "mesh_echo_test.py"
    assert installed.exists()
    installed.unlink()


def test_bundle_with_tampered_code_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus.mesh import identity as ident_mod
    from nexus.mesh import sync as sync_mod
    importlib.reload(ident_mod)
    importlib.reload(sync_mod)

    ident = ident_mod.new_identity(label="producer")
    ident_mod.add_peer(pubkey_b64=ident.pubkey_b64, label="producer", url="http://x")

    ms = sync_mod.MeshSkill(
        id="x",
        file_hash="sha256:deadbeef",  # wrong hash
        code="from nexus.skills.base import Skill, SkillContext\n\nclass X(Skill):\n    id='x'\n    def execute(self,ctx,i):return {}",
    )
    bundle = sync_mod.SkillBundle(
        bundle_id="b1",
        producer=ident.pubkey_b64,
        produced_ts=0.0,
        skills=[ms],
    )
    bundle.signature = ident_mod.sign(bundle.canonical_payload(), identity=ident)

    report = sync_mod.install_bundle(bundle)
    assert not report["ok"]
