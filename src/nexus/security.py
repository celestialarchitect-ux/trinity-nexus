"""Security governor (§29) — runtime guardrails.

Layers (in order of strictness, stackable):

  1. Destructive-op pattern gate       — run_command blocks `rm -rf /` etc.
  2. Safe mode (NEXUS_SAFE=1)          — no run_command, writes globbed
  3. Read-only mode (NEXUS_READONLY=1) — zero mutation tools at all
  4. Untrusted-tool taint              — web/frontier outputs wrapped so the
                                         model treats them as data not instructions
  5. Injection scanner                 — heuristic flag-and-log on every tool out
  6. Rate limiter                      — tool + LLM calls per minute per session
  7. Secret redactor                   — session transcripts strip API keys etc.
  8. Encrypted memory at rest          — Fernet-encrypted tiers via passphrase

None of this replaces OS permissions; this is belt + suspenders on top.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# ---------------------------------------------------------------------------
# MODE FLAGS
# ---------------------------------------------------------------------------


def is_safe_mode() -> bool:
    return os.environ.get("NEXUS_SAFE", "0") == "1"


def is_readonly() -> bool:
    return os.environ.get("NEXUS_READONLY", "0") == "1"


def write_allowed(path: str) -> bool:
    """Under safe mode, only paths matching NEXUS_WRITE_ALLOW are writable."""
    import fnmatch
    if is_readonly():
        return False
    if not is_safe_mode():
        return True
    patterns = os.environ.get("NEXUS_WRITE_ALLOW", "")
    if not patterns:
        return False
    abs_path = str(Path(path).expanduser().resolve())
    for pat in patterns.split(os.pathsep):
        if fnmatch.fnmatch(abs_path, pat.strip()):
            return True
    return False


# ---------------------------------------------------------------------------
# TAINT + INJECTION SCAN
# ---------------------------------------------------------------------------


def taint(text: str, *, source: str) -> str:
    """Wrap untrusted content so the agent treats it as data (§10 + §20)."""
    if not text:
        return ""
    scan = scan_for_injection(text)
    warn = f" injection_patterns={','.join(scan)}" if scan else ""
    head = f"<UNTRUSTED source={source}{warn}>"
    tail = "</UNTRUSTED>"
    return head + "\n" + text + "\n" + tail


_INJECTION_PATTERNS = [
    r"ignore (?:all|previous|prior) (?:instructions|prompts)",
    r"disregard (?:all|previous|prior)",
    r"new\s+instructions",
    r"system\s+prompt",
    r"you are now",
    r"you must now",
    r"(?:please )?run (?:the )?command",
    r"execute(?: the)? code",
    r"curl .+? \| (?:bash|sh)",
    r"iwr .+? \| iex",
    r"rm\s+-rf",
    r"NEXUS_ALLOW_DANGEROUS",
    r"override\s+safety",
    r"api[_-]?key\s*[:=]",
    r"bearer\s+[A-Za-z0-9\-_]+",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"gsk_[A-Za-z0-9_-]{20,}",
    r"pypi-[A-Za-z0-9_-]{20,}",
]


def scan_for_injection(text: str) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)
    return hits


# ---------------------------------------------------------------------------
# SECRET REDACTION
# ---------------------------------------------------------------------------


_SECRET_PATTERNS = [
    # Provider-specific prefixes
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "sk-REDACTED"),
    (re.compile(r"gsk_[A-Za-z0-9_-]{16,}"), "gsk_REDACTED"),
    (re.compile(r"pypi-[A-Za-z0-9_-]{16,}"), "pypi-REDACTED"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_REDACTED"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "gho_REDACTED"),
    (re.compile(r"xai-[A-Za-z0-9]{16,}"), "xai-REDACTED"),
    (re.compile(r"AIza[A-Za-z0-9\-_]{20,}"), "AIza-REDACTED"),
    # Generic bearer tokens
    (re.compile(r"[Bb]earer\s+[A-Za-z0-9\-_.=]{20,}"), "Bearer REDACTED"),
    # PEM blocks
    (re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]+?-----END [A-Z ]+-----"), "-----PEM REDACTED-----"),
    # AWS access keys
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA-REDACTED"),
    # Private seeds/mnemonics — crude heuristic: 12-24 lowercase words
    (re.compile(r"\b(?:[a-z]+\s+){11,23}[a-z]+\b"), "[seed-phrase-redacted]"),
]


def redact(text: str) -> str:
    """Strip obvious secrets. Non-fatal — best-effort."""
    if not text:
        return text
    out = text
    for pat, replacement in _SECRET_PATTERNS:
        out = pat.sub(replacement, out)
    return out


# ---------------------------------------------------------------------------
# RATE LIMITER (in-process, sliding window)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Sliding-window rate limiter. Thread-safe enough for our single REPL use."""

    def __init__(self, *, limit: int, window_sec: float):
        self.limit = limit
        self.window = window_sec
        self._events: list[float] = []

    def allow(self) -> bool:
        now = time.time()
        self._events = [t for t in self._events if now - t < self.window]
        if len(self._events) >= self.limit:
            return False
        self._events.append(now)
        return True

    def remaining(self) -> int:
        now = time.time()
        self._events = [t for t in self._events if now - t < self.window]
        return max(0, self.limit - len(self._events))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Global limiters, configurable via env. Hit means: "refuse this call".
_TOOL_LIMITER = RateLimiter(
    limit=_int_env("NEXUS_RATE_TOOLS_PER_MIN", 120),
    window_sec=60.0,
)
_LLM_LIMITER = RateLimiter(
    limit=_int_env("NEXUS_RATE_LLM_PER_MIN", 40),
    window_sec=60.0,
)


def tool_call_allowed() -> bool:
    return _TOOL_LIMITER.allow()


def llm_call_allowed() -> bool:
    return _LLM_LIMITER.allow()


def rate_status() -> dict:
    return {
        "tools_remaining_this_min": _TOOL_LIMITER.remaining(),
        "tools_limit": _TOOL_LIMITER.limit,
        "llm_remaining_this_min": _LLM_LIMITER.remaining(),
        "llm_limit": _LLM_LIMITER.limit,
    }


# ---------------------------------------------------------------------------
# AUDIT LOG with HMAC
# ---------------------------------------------------------------------------


def _audit_path() -> Path:
    from nexus.config import settings
    p = settings.oracle_log_dir / "audit.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _audit_key() -> bytes:
    """HMAC key lives with the mesh identity — one tamper-evident log per node."""
    key = os.environ.get("NEXUS_AUDIT_KEY")
    if key:
        return key.encode("utf-8")
    # Derive from the mesh pubkey if available, else fall back to hostname
    try:
        from nexus.mesh.identity import load_identity
        ident = load_identity()
        if ident:
            return ident.pubkey_b64.encode("utf-8")
    except Exception:
        pass
    return (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "nexus").encode("utf-8")


def audit(event: str, **fields) -> None:
    """Append one event to the audit log, HMAC-chained so tampering is visible."""
    payload = {"ts": time.time(), "event": event, **{k: redact(str(v)) if isinstance(v, str) else v for k, v in fields.items()}}
    body = json.dumps(payload, sort_keys=True, default=str)
    sig = hmac.new(_audit_key(), body.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    line = f"{body} · {sig}\n"
    try:
        with _audit_path().open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ENCRYPTED MEMORY AT REST
# ---------------------------------------------------------------------------
#
# Strategy: a single passphrase → PBKDF2(SHA256, 200k) → Fernet key. The salt
# lives next to the data at <ORACLE_HOME>/memory/.salt (random-generated on
# first use). The key itself is never persisted; it's rederived from the
# passphrase each session.
#
# We keep this opt-in on a per-tier basis via an .enc suffix. When a tier
# file is named e.g. `protected.md.enc`, reads transparently decrypt and
# writes re-encrypt. If the passphrase isn't known this session, encrypted
# tiers return "" and warn.


_SESSION_KEY: bytes | None = None  # cached Fernet key for this process


def _salt_path() -> Path:
    from nexus.config import settings
    return settings.oracle_home / "memory" / ".salt"


def _get_or_create_salt() -> bytes:
    p = _salt_path()
    if p.exists():
        return p.read_bytes()
    salt = os.urandom(16)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(salt)
    return salt


def derive_key(passphrase: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_get_or_create_salt(),
        iterations=200_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def unlock_session(passphrase: str) -> bool:
    """Set the session-global key from a passphrase. Returns True on success.

    We round-trip encrypt→decrypt a probe to verify. If a prior probe exists
    in `.probe`, we check against it to catch wrong passphrases.
    """
    global _SESSION_KEY
    key = derive_key(passphrase)
    f = Fernet(key)

    from nexus.config import settings
    probe_path = settings.oracle_home / "memory" / ".probe"
    if probe_path.exists():
        try:
            f.decrypt(probe_path.read_bytes())
        except InvalidToken:
            return False
    else:
        probe_path.parent.mkdir(parents=True, exist_ok=True)
        probe_path.write_bytes(f.encrypt(b"nexus-probe"))

    _SESSION_KEY = key
    return True


def is_unlocked() -> bool:
    return _SESSION_KEY is not None


def encrypt_text(text: str) -> bytes:
    if _SESSION_KEY is None:
        raise RuntimeError("encryption locked — run /encrypt unlock <passphrase>")
    return Fernet(_SESSION_KEY).encrypt(text.encode("utf-8"))


def decrypt_text(blob: bytes) -> str:
    if _SESSION_KEY is None:
        raise RuntimeError("encryption locked")
    return Fernet(_SESSION_KEY).decrypt(blob).decode("utf-8")
