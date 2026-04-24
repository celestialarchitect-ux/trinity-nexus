"""Built-in tools for the Oracle agent.

Mirrors Claude Code's tool set: file I/O, shell, glob/grep search, web fetch
+ search, plus Oracle-specific memory tools. Stays tight (<20 tools) so the
model's tool-choice remains crisp.
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import os
import platform
import re
import subprocess
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import tool

MAX_READ_BYTES = 256_000
MAX_EDIT_BYTES = 1_000_000
MAX_HTTP_BYTES = 600_000


# ---------- time / system ----------


@tool
def get_time(timezone: str = "local") -> str:
    """Return the current date and time. `timezone` accepts 'local' or 'utc'."""
    now = _dt.datetime.now(_dt.UTC) if timezone == "utc" else _dt.datetime.now()
    return now.isoformat(timespec="seconds")


@tool
def system_info() -> dict[str, str]:
    """Return host machine information: OS, CPU, Python version, cwd."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "node": platform.node(),
        "cwd": os.getcwd(),
    }


# §29 — patterns that should never run without explicit user unlock.
_DANGEROUS_PATTERNS = [
    r"\brm\s+-rf?\s+/",
    r"\brm\s+-rf?\s+\*",
    r"\brm\s+-rf?\s+~",
    r"\bmkfs\b",
    r"\bdd\s+if=.*\bof=/dev",
    r":\(\)\s*\{.*:\|:&\s*\};:",            # classic fork-bomb
    r"\bshutdown\b",
    r"\bhalt\b",
    r"\breboot\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-f\w*d",
    r"\bgit\s+push\s+.*--force\b",
    r"\bDROP\s+(TABLE|DATABASE)\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bdocker\s+system\s+prune",
    r"\bkubectl\s+delete\b",
    r"\bformat\s+[A-Za-z]:",                # Windows format
]


def _is_dangerous(cmd: str) -> str | None:
    if os.environ.get("NEXUS_ALLOW_DANGEROUS") == "1":
        return None
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, cmd, flags=re.IGNORECASE):
            return pat
    return None


@tool
def run_command(command: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Execute a shell command. Returns {stdout, stderr, returncode}.

    Destructive commands are blocked by default (§29 Security Governor). Set
    `NEXUS_ALLOW_DANGEROUS=1` or run `/dangerous` in the REPL to unlock.
    """
    danger = _is_dangerous(command)
    if danger:
        return {
            "stdout": "",
            "stderr": (
                f"[blocked §29] command matches destructive pattern ({danger}). "
                "Set NEXUS_ALLOW_DANGEROUS=1 or run /dangerous to override."
            ),
            "returncode": -3,
        }
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return {
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "timeout", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": f"{type(e).__name__}: {e}", "returncode": -2}


# ---------- files ----------


def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


@tool
def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read a text file. `end_line=0` means read to the end.

    Returns content with `N: ` line-number prefixes (so the model can edit precisely).
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"error: no such file: {p}"
        if p.stat().st_size > MAX_READ_BYTES:
            return f"error: file too large ({p.stat().st_size:,} bytes > {MAX_READ_BYTES:,})"
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        s = max(1, int(start_line))
        e = len(lines) if int(end_line) in (0, -1) else min(len(lines), int(end_line))
        if s > len(lines):
            return f"error: start_line {s} > file has {len(lines)} lines"
        width = len(str(e))
        return "\n".join(f"{i:>{width}}: {lines[i-1]}" for i in range(s, e + 1))
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file. Parent directories are created as needed."""
    try:
        p = _resolve(path)
        if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
            return f"error: content exceeds {MAX_EDIT_BYTES:,} bytes"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {p}"
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace the first occurrence of `old_string` with `new_string` in a file.

    First tries exact match; on whitespace-drift, normalises indentation and
    retries. Fails if `old_string` appears zero or >1 times — caller must
    provide enough surrounding context to make the match unique.
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"error: no such file: {p}"
        text = p.read_text(encoding="utf-8")

        # Exact
        count = text.count(old_string)
        if count == 1:
            p.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
            return f"edited {p} (1 replacement)"
        if count > 1:
            return f"error: old_string appears {count} times — add more context to make it unique"

        # Whitespace-tolerant fallback: normalise leading indentation
        def _normalise(s: str) -> str:
            lines = s.splitlines()
            # Strip common leading whitespace
            non_empty = [ln for ln in lines if ln.strip()]
            if not non_empty:
                return s
            indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
            return "\n".join(ln[indent:] if ln.strip() else "" for ln in lines)

        norm_old = _normalise(old_string)
        norm_text = _normalise(text)
        if norm_text.count(norm_old) == 1:
            # Locate in the normalised version, then map back to original
            idx = norm_text.index(norm_old)
            # Rough mapping via cumulative line length
            orig_lines = text.splitlines(keepends=True)
            norm_lines = norm_text.splitlines(keepends=True)
            char_count = 0
            start_line = 0
            for i, ln in enumerate(norm_lines):
                if char_count >= idx:
                    start_line = i
                    break
                char_count += len(ln)
            else:
                start_line = len(norm_lines) - 1
            end_line = start_line + len(norm_old.splitlines())
            new_lines = orig_lines[:start_line] + [new_string + ("\n" if not new_string.endswith("\n") else "")] + orig_lines[end_line:]
            p.write_text("".join(new_lines), encoding="utf-8")
            return f"edited {p} (1 replacement, whitespace-tolerant)"

        return "error: old_string not found in file (even after whitespace normalisation)"
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@tool
def apply_diff(path: str, search: str, replace: str) -> str:
    """SEARCH/REPLACE-block edit — aider's format, more robust than edit_file.

    `search` is the exact current text (must match once). `replace` is what
    replaces it. Use this when edit_file fails due to drift or when you want
    to make a clearly-bounded change. Returns a line-count delta on success.
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"error: no such file: {p}"
        text = p.read_text(encoding="utf-8")
        count = text.count(search)
        if count == 0:
            # try stripping trailing whitespace on each line
            norm_search = "\n".join(ln.rstrip() for ln in search.splitlines())
            norm_text = "\n".join(ln.rstrip() for ln in text.splitlines())
            if norm_text.count(norm_search) == 1:
                # replace in normalised then write whole normalised text
                new_norm = norm_text.replace(norm_search, replace, 1)
                p.write_text(new_norm, encoding="utf-8")
                return f"applied diff to {p} (normalised whitespace)"
            return "error: search block not found"
        if count > 1:
            return f"error: search block appears {count} times — widen the context"
        p.write_text(text.replace(search, replace, 1), encoding="utf-8")
        delta = replace.count("\n") - search.count("\n")
        sign = "+" if delta >= 0 else ""
        return f"applied diff to {p} ({sign}{delta} lines)"
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@tool
def glob_paths(pattern: str, root: str = ".") -> list[str]:
    """List files matching a glob pattern under `root`, sorted by mtime (newest first).

    Example patterns: `**/*.py`, `src/**/*.ts`, `*.md`.
    Common dirs (.git, __pycache__, node_modules, .venv) are skipped.
    """
    skip = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build"}
    rootp = _resolve(root)
    if not rootp.exists():
        return [f"error: {rootp} does not exist"]
    hits: list[tuple[float, str]] = []
    for p in rootp.rglob("*"):
        if any(part in skip for part in p.parts):
            continue
        rel = p.relative_to(rootp).as_posix()
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
            try:
                hits.append((p.stat().st_mtime, str(p)))
            except OSError:
                continue
        if len(hits) > 500:
            break
    hits.sort(reverse=True)
    return [h[1] for h in hits[:200]]


@tool
def grep_files(
    pattern: str,
    path: str = ".",
    glob: str = "*",
    max_results: int = 50,
) -> list[dict]:
    """Search for a regex pattern in files. Returns list of {file, line, text} matches.

    `glob` filters by filename (e.g. `*.py`). Case-sensitive. Use `(?i)` in the
    pattern for case-insensitive search.
    """
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return [{"error": f"bad regex: {e}"}]

    rootp = _resolve(path)
    if not rootp.exists():
        return [{"error": f"{rootp} does not exist"}]

    skip = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build"}
    matches: list[dict] = []
    files = [rootp] if rootp.is_file() else rootp.rglob(glob)
    for p in files:
        if not p.is_file():
            continue
        if any(part in skip for part in p.parts):
            continue
        try:
            if p.stat().st_size > 2_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"file": str(p), "line": i, "text": line[:300]})
                if len(matches) >= max_results:
                    return matches
    return matches


# ---------- web ----------


class _TextExtractor(HTMLParser):
    """Strip script/style, keep visible text. Keeps things small and fast."""

    def __init__(self):
        super().__init__()
        self._skip = 0
        self._out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "iframe"} and self._skip:
            self._skip -= 1
        if tag in {"p", "br", "h1", "h2", "h3", "h4", "h5", "li", "div", "tr"}:
            self._out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._out.append(data)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._out)).strip()


@tool
def web_fetch(url: str, max_chars: int = 4000) -> str:
    """Fetch a URL and return extracted text content (JS-stripped). Follows redirects."""
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers={"User-Agent": "Mozilla/5.0 OracleBot/1.0"},
        ) as client:
            r = client.get(url)
        if r.status_code >= 400:
            return f"error: HTTP {r.status_code}"
        ct = r.headers.get("content-type", "")
        body = r.text[:MAX_HTTP_BYTES]
        if "html" not in ct.lower():
            return body[:max_chars]
        parser = _TextExtractor()
        parser.feed(body)
        text = parser.text()
        return text[:max_chars] if len(text) > max_chars else text
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@tool
def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Search the web via DuckDuckGo HTML. No API key required. Returns {title, url, snippet}."""
    try:
        resp = httpx.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
        # Crude but reliable: pull result blocks. DDG HTML format is stable enough.
        results: list[dict] = []
        for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html,
            flags=re.DOTALL,
        ):
            raw_url, title, snippet = m.group(1), m.group(2), m.group(3)
            # DDG wraps real URL in a redirect: ?uddg=<urlencoded>
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            real = qs.get("uddg", [raw_url])[0]
            results.append(
                {
                    "title": re.sub(r"<[^>]+>", "", title).strip(),
                    "url": real,
                    "snippet": re.sub(r"<[^>]+>", "", snippet).strip()[:300],
                }
            )
            if len(results) >= max_results:
                break
        return results or [{"note": "no results or DDG HTML format changed"}]
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}"}]


# ---------- memory ----------


@tool
def remember(fact: str, tags: str = "") -> str:
    """Store a durable fact in Trinity Nexus's archival memory. `tags` is comma-separated.

    Prefer tagging with one of mind/soul/body (§07) plus a topical tag.
    """
    from nexus.memory import MemoryTiers

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    mid = MemoryTiers().remember(fact, tags=tag_list, source="agent")
    return f"remembered: id={mid} {fact[:80]}"


# ---------- sub-agent (§19) ----------


@tool
def spawn_agent(task: str, thread_id: str = "") -> str:
    """Spawn a sub-Nexus to run a self-contained task and return its final answer.

    The sub-agent shares archival memory (so it can retrieve and remember) but
    runs on its own thread so its conversation doesn't pollute the parent's
    context. Use for: parallel research, focused sub-tasks, evaluator runs,
    anything that would otherwise blow the parent's context budget.
    """
    from nexus.agent import Oracle  # local import to avoid circular
    import uuid as _uuid

    tid = thread_id or f"sub-{_uuid.uuid4().hex[:10]}"
    sub = Oracle(thread_id=tid)
    try:
        answer = sub.ask(task)
    finally:
        sub.close()
    return (answer or "")[:8000]


# ---------- registry ----------


BUILTIN_TOOLS = [
    # time / system
    get_time,
    system_info,
    run_command,
    # files
    read_file,
    write_file,
    edit_file,
    apply_diff,
    glob_paths,
    grep_files,
    # web
    web_fetch,
    web_search,
    # memory
    remember,
    # sub-agent
    spawn_agent,
]
