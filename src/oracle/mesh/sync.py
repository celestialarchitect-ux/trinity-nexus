"""Skill bundle build + push + pull.

Bundle format (JSON):
{
  "bundle_id":   "<uuid>",
  "producer":    "<pubkey_b64>",
  "produced_ts": <epoch>,
  "skills": [
    {
      "id":         "<skill_id>",
      "file_hash":  "sha256:<hex>",
      "code":       "<python source>",
      "origin":     "self_written|seed",
      "confidence": <float>
    }, ...
  ],
  "signature": "<b64 ed25519 sig over canonicalized bundle minus signature>"
}

On pull, the receiver:
  1. parses the bundle,
  2. verifies producer pubkey is in the local allowlist,
  3. verifies the signature covers the canonical payload,
  4. verifies each skill's file_hash matches code,
  5. runs the same syntactic check as evolve.py,
  6. installs accepted skills to `skills/mesh/`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from oracle.mesh.identity import (
    PeerIdentity,
    is_trusted,
    load_identity,
    sign,
    verify,
)
from oracle.skills.evolve import _syntactic_check
from oracle.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

MESH_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills" / "mesh"
MESH_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
_init = MESH_SKILLS_DIR / "__init__.py"
if not _init.exists():
    _init.write_text("# Skills pulled from trusted mesh peers.\n", encoding="utf-8")


def _sha256_hex(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class MeshSkill:
    id: str
    file_hash: str
    code: str
    origin: str = "mesh"
    confidence: float = 0.4


@dataclass
class SkillBundle:
    bundle_id: str
    producer: str
    produced_ts: float
    skills: list[MeshSkill] = field(default_factory=list)
    signature: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "producer": self.producer,
            "produced_ts": self.produced_ts,
            "skills": [asdict(s) for s in self.skills],
            "signature": self.signature,
        }

    def canonical_payload(self) -> bytes:
        """Stable bytes to sign/verify — MUST NOT include signature."""
        obj = {
            "bundle_id": self.bundle_id,
            "producer": self.producer,
            "produced_ts": self.produced_ts,
            "skills": [asdict(s) for s in self.skills],
        }
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_bundle(
    *,
    identity: PeerIdentity | None = None,
    include_origins: tuple[str, ...] = ("self_written",),
) -> SkillBundle:
    """Package local skills (by default only self-written) into a signed bundle."""
    ident = identity or load_identity()
    if not ident:
        raise RuntimeError("no mesh identity — run `oracle mesh keygen` first")

    reg = SkillRegistry()
    reg.load_all()

    mesh_skills: list[MeshSkill] = []
    for s in reg.all():
        if s.origin not in include_origins:
            continue
        # Locate source file by module attribute or seed path
        src_file = _locate_source(s)
        if not src_file or not src_file.exists():
            continue
        code = src_file.read_text(encoding="utf-8")
        mesh_skills.append(
            MeshSkill(
                id=s.id,
                file_hash=_sha256_hex(code),
                code=code,
                origin=s.origin,
                confidence=round(s.confidence, 3),
            )
        )

    bundle = SkillBundle(
        bundle_id=str(uuid.uuid4()),
        producer=ident.pubkey_b64,
        produced_ts=time.time(),
        skills=mesh_skills,
    )
    bundle.signature = sign(bundle.canonical_payload(), identity=ident)
    return bundle


def _locate_source(skill) -> Path | None:
    """Best-effort: find the .py file that registered this skill."""
    import sys as _sys

    mod = _sys.modules.get(f"oracle_skill_{skill.__class__.__module__.split('.')[-1]}")
    if mod and getattr(mod, "__file__", None):
        return Path(mod.__file__)
    # Try the registry's known roots
    base = Path(__file__).resolve().parents[1] / "skills"
    for root in (base / "evolved", base / "mesh", base / "seed"):
        cand = root / f"{skill.id}.py"
        if cand.exists():
            return cand
    # Last resort: search any .py that matches
    for p in base.rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
            if f'id = "{skill.id}"' in text or f"id = '{skill.id}'" in text:
                return p
        except Exception:
            continue
    return None


def _verify_bundle(bundle: SkillBundle) -> list[str]:
    """Return a list of rejection reasons. Empty list == trusted + intact."""
    reasons: list[str] = []
    if not is_trusted(bundle.producer):
        reasons.append(f"producer {bundle.producer[:12]}… not in allowlist")
        return reasons  # don't even check the sig
    if not verify(
        bundle.canonical_payload(),
        signature_b64=bundle.signature,
        pubkey_b64=bundle.producer,
    ):
        reasons.append("signature verification failed")
        return reasons
    for s in bundle.skills:
        if _sha256_hex(s.code) != s.file_hash:
            reasons.append(f"{s.id}: file_hash mismatch")
        syn = _syntactic_check(s.code)
        if syn:
            reasons.append(f"{s.id}: {syn}")
    return reasons


def install_bundle(bundle: SkillBundle) -> dict:
    """Verify + install. Returns a report dict."""
    reasons = _verify_bundle(bundle)
    installed: list[str] = []
    rejected: list[dict] = []

    if reasons:
        return {
            "ok": False,
            "bundle_id": bundle.bundle_id,
            "installed": installed,
            "rejected": [{"bundle_reasons": reasons}],
        }

    for s in bundle.skills:
        target = MESH_SKILLS_DIR / f"{s.id}.py"
        try:
            target.write_text(s.code, encoding="utf-8")
            installed.append(s.id)
        except Exception as e:
            rejected.append({"id": s.id, "reason": f"write failed: {e}"})

    return {
        "ok": bool(installed),
        "bundle_id": bundle.bundle_id,
        "installed": installed,
        "rejected": rejected,
    }


def push_bundle(
    *,
    peer_url: str,
    identity: PeerIdentity | None = None,
    include_origins: tuple[str, ...] = ("self_written",),
    timeout: float = 30.0,
) -> dict:
    bundle = build_bundle(identity=identity, include_origins=include_origins)
    r = httpx.post(
        peer_url.rstrip("/") + "/api/mesh/push",
        json=bundle.to_dict(),
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def pull_bundle(
    *,
    peer_url: str,
    timeout: float = 30.0,
) -> dict:
    r = httpx.get(peer_url.rstrip("/") + "/api/mesh/export", timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    bundle = SkillBundle(
        bundle_id=payload["bundle_id"],
        producer=payload["producer"],
        produced_ts=float(payload["produced_ts"]),
        skills=[MeshSkill(**s) for s in payload.get("skills", [])],
        signature=payload.get("signature", ""),
    )
    return install_bundle(bundle)
