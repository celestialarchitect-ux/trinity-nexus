"""Oracle — sovereign personal AI prototype."""

from __future__ import annotations

import io as _io
import sys as _sys

__version__ = "0.1.0"

# Force UTF-8 on Windows consoles so Unicode banner + qwen3 output render right.
# Applied on package import so every entry point (CLI, REPL, tests) gets it.
if _sys.platform == "win32":
    for _stream in (_sys.stdout, _sys.stderr):
        if isinstance(_stream, _io.TextIOWrapper) and _stream.encoding and _stream.encoding.lower() != "utf-8":
            try:
                _stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

