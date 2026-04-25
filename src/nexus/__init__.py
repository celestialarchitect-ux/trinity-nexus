"""Trinity Nexus — sovereign adaptive intelligence (Omega Foundation 1.0)."""

from __future__ import annotations

import io as _io
import os as _os
import sys as _sys

__version__ = "1.0.31"

# Cap BLAS thread pools BEFORE numpy/scipy/torch imports below the line.
# OpenBLAS (and friends) eagerly allocate a per-thread workspace pool when
# the library is first loaded — typically ~64MB per thread. On a 16-core
# box that's 1GB+ of contiguous virtual address space requested up front,
# and on Windows after a model-load thrash that contiguous block isn't
# always available, producing:
#   "OpenBLAS error: Memory allocation still failed after 10 retries..."
# and killing `nexus` before it can print its banner. We pin every
# common BLAS lib to 4 threads (plenty for our embed/vector ops, since
# heavy matmul lives on the GPU via Ollama) — drop to 1 if you still
# see allocation failures. Users who actually want the BLAS parallelism
# can override any of these in their environment.
for _var, _default in (
    ("OPENBLAS_NUM_THREADS", "4"),
    ("OMP_NUM_THREADS", "4"),
    ("MKL_NUM_THREADS", "4"),
    ("VECLIB_MAXIMUM_THREADS", "4"),
    ("NUMEXPR_NUM_THREADS", "4"),
):
    _os.environ.setdefault(_var, _default)

# Force UTF-8 on Windows consoles so Unicode banner + qwen3 output render right.
# Applied on package import so every entry point (CLI, REPL, tests) gets it.
if _sys.platform == "win32":
    for _stream in (_sys.stdout, _sys.stderr):
        if isinstance(_stream, _io.TextIOWrapper) and _stream.encoding and _stream.encoding.lower() != "utf-8":
            try:
                _stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

