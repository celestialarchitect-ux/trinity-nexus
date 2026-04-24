"""Per-tool glob/regex allow-deny permission model (§29).

Inspired by Claude Code's `settings.json` permission system + cline's
approval loop. Three precedence tiers:

  1. explicit DENY (pattern match) → blocked, no prompt
  2. explicit ALLOW (pattern match) → passes
  3. default → deny for write/shell, allow for read

Persisted TOML at `~/.nexus/permissions.toml`:

    [rules]
    "bash:git *"       = "allow"
    "bash:rm -rf *"    = "deny"
    "write:./src/**"   = "allow"
    "read:.env"        = "deny"

Keys are `<tool>:<pattern>`. Pattern uses fnmatch glob semantics.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


PERMISSIONS_PATH = Path.home() / ".nexus" / "permissions.toml"

DEFAULT_ALLOW_TOOLS = {"read", "glob", "grep", "web_fetch", "web_search", "get_time", "system_info"}
# Everything else defaults to deny unless an explicit allow exists.


@dataclass
class Decision:
    ok: bool
    reason: str


def _read_rules() -> dict[str, str]:
    if not PERMISSIONS_PATH.exists():
        return {}
    try:
        data = tomllib.loads(PERMISSIONS_PATH.read_text(encoding="utf-8"))
        return {k: str(v).lower() for k, v in (data.get("rules") or {}).items()}
    except Exception:
        return {}


def _write_rules(rules: dict[str, str]) -> None:
    PERMISSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[rules]"]
    for k, v in sorted(rules.items()):
        lines.append(f'"{k}" = "{v}"')
    PERMISSIONS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check(tool: str, target: str) -> Decision:
    """Return the permission decision for `tool` operating on `target`.

    `tool` is one of: bash, write, edit, read, glob, grep, web_fetch,
    web_search, spawn_agent, remember, retrieve, etc.
    `target` is the thing being acted on — a command, a path, a URL.
    """
    rules = _read_rules()

    # 1. explicit deny wins
    for key, verdict in rules.items():
        if not key.startswith(f"{tool}:"):
            continue
        pattern = key[len(tool) + 1:]
        if fnmatch.fnmatch(target, pattern) and verdict == "deny":
            return Decision(ok=False, reason=f"denied by rule {tool}:{pattern}")

    # 2. explicit allow
    for key, verdict in rules.items():
        if not key.startswith(f"{tool}:"):
            continue
        pattern = key[len(tool) + 1:]
        if fnmatch.fnmatch(target, pattern) and verdict == "allow":
            return Decision(ok=True, reason=f"allowed by rule {tool}:{pattern}")

    # 3. defaults — read-family allowed, mutation denied
    if tool in DEFAULT_ALLOW_TOOLS:
        return Decision(ok=True, reason="default: read-family")
    return Decision(
        ok=False,
        reason=f"no rule for {tool}:{target!r}; add with /allow {tool} <pattern>",
    )


def allow(tool: str, pattern: str) -> None:
    rules = _read_rules()
    rules[f"{tool}:{pattern}"] = "allow"
    _write_rules(rules)


def deny(tool: str, pattern: str) -> None:
    rules = _read_rules()
    rules[f"{tool}:{pattern}"] = "deny"
    _write_rules(rules)


def remove(tool: str, pattern: str) -> bool:
    rules = _read_rules()
    key = f"{tool}:{pattern}"
    if key in rules:
        del rules[key]
        _write_rules(rules)
        return True
    return False


def list_rules() -> list[tuple[str, str, str]]:
    """Return [(tool, pattern, verdict), …]."""
    out: list[tuple[str, str, str]] = []
    for key, verdict in _read_rules().items():
        if ":" not in key:
            continue
        tool, pattern = key.split(":", 1)
        out.append((tool, pattern, verdict))
    return sorted(out)
