"""Ed25519 keypair identity for Oracle mesh nodes.

Uses the `cryptography` library (already an install-time dep). Keys live at
`$ORACLE_HOME/mesh/key.json` with a base64url-encoded private + public key.

We intentionally do NOT encrypt the private key at rest in v1 — this is a
local-first system running on the user's own box. For shared hardware or
multi-user setups, wrap with OS keychain / Windows DPAPI.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from oracle.config import settings


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@dataclass
class PeerIdentity:
    pubkey_b64: str
    privkey_b64: str
    created_ts: float
    label: str = "nexus-pc"

    def sign(self, data: bytes) -> str:
        sk = ed25519.Ed25519PrivateKey.from_private_bytes(_b64d(self.privkey_b64))
        return _b64(sk.sign(data))

    def public(self) -> str:
        return self.pubkey_b64


def default_key_path() -> Path:
    p = settings.oracle_home / "mesh" / "key.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def new_identity(*, label: str = "nexus-pc", path: Path | None = None) -> PeerIdentity:
    """Generate a keypair and persist it. Overwrites existing file."""
    sk = ed25519.Ed25519PrivateKey.generate()
    pk = sk.public_key()

    priv_bytes = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = pk.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    ident = PeerIdentity(
        pubkey_b64=_b64(pub_bytes),
        privkey_b64=_b64(priv_bytes),
        created_ts=time.time(),
        label=label,
    )
    p = path or default_key_path()
    p.write_text(
        json.dumps(
            {
                "pubkey_b64": ident.pubkey_b64,
                "privkey_b64": ident.privkey_b64,
                "created_ts": ident.created_ts,
                "label": ident.label,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return ident


def load_identity(path: Path | None = None) -> PeerIdentity | None:
    p = path or default_key_path()
    if not p.exists():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    return PeerIdentity(
        pubkey_b64=obj["pubkey_b64"],
        privkey_b64=obj["privkey_b64"],
        created_ts=float(obj.get("created_ts", 0.0)),
        label=obj.get("label", "peer"),
    )


def sign(data: bytes, *, identity: PeerIdentity) -> str:
    return identity.sign(data)


def verify(data: bytes, *, signature_b64: str, pubkey_b64: str) -> bool:
    try:
        pk = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(pubkey_b64))
        pk.verify(_b64d(signature_b64), data)
        return True
    except (InvalidSignature, Exception):
        return False


def allowlist_path() -> Path:
    p = settings.oracle_home / "mesh" / "peers.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(json.dumps({"peers": []}, indent=2), encoding="utf-8")
    return p


def load_allowlist() -> list[dict]:
    p = allowlist_path()
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("peers", [])
    except Exception:
        return []


def add_peer(*, pubkey_b64: str, label: str, url: str) -> None:
    p = allowlist_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"peers": []}
    peers = data.get("peers", [])
    for existing in peers:
        if existing.get("pubkey_b64") == pubkey_b64:
            existing.update({"label": label, "url": url})
            break
    else:
        peers.append(
            {"pubkey_b64": pubkey_b64, "label": label, "url": url, "added_ts": time.time()}
        )
    data["peers"] = peers
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_trusted(pubkey_b64: str) -> bool:
    return any(p.get("pubkey_b64") == pubkey_b64 for p in load_allowlist())
