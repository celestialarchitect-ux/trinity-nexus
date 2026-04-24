"""ORACLE banner — retro neon purple on startup.

Rendered with Rich so it auto-disables color on non-ANSI terminals. Uses only
the solid-block char `█` (U+2588) plus space — renders correctly in every
monospace font (Cascadia, Consolas, JetBrains Mono, Menlo, etc.).

Switch styles with `ORACLE_BANNER=pixel|shadow|off` in your env.
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.text import Text


# Hand-crafted pixel-block "ORACLE" — pure arcade / 8-bit look.
# Each letter is 5 rows tall. `█` and space only.
PIXEL_ORACLE = [
    "██████  ██████   █████   ██████ ██      ███████",
    "██   ██ ██   ██ ██   ██ ██      ██      ██     ",
    "██   ██ ██████  ███████ ██      ██      █████  ",
    "██   ██ ██   ██ ██   ██ ██      ██      ██     ",
    "██████  ██   ██ ██   ██  ██████ ███████ ███████",
]

# Classic figlet "ANSI Shadow" — thinner, more futuristic. Uses box-drawing.
SHADOW_ORACLE = [
    r" ██████╗ ██████╗  █████╗  ██████╗██╗     ███████╗",
    r"██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║     ██╔════╝",
    r"██║   ██║██████╔╝███████║██║     ██║     █████╗  ",
    r"██║   ██║██╔══██╗██╔══██║██║     ██║     ██╔══╝  ",
    r"╚██████╔╝██║  ██║██║  ██║╚██████╗███████╗███████╗",
    r" ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚══════╝",
]

# Neon purple gradient (top → bottom). CRT arcade feel.
NEON_COLORS = [
    "#c77dff",
    "#b23bf2",
    "#9d00ff",
    "#7b00e0",
    "#6a00c2",
    "#5a00a8",
]


def render_banner(
    *,
    console: Console,
    model: str = "",
    device: str = "",
    version: str = "",
) -> None:
    """Print the startup banner. Silent on non-terminal output."""
    style = os.environ.get("ORACLE_BANNER", "pixel").lower().strip()
    if style == "off":
        return

    if not console.is_terminal:
        console.print(f"Oracle v{version} · {model} · {device}")
        return

    lines = SHADOW_ORACLE if style == "shadow" else PIXEL_ORACLE

    body = Text()
    for i, line in enumerate(lines):
        color = NEON_COLORS[min(i, len(NEON_COLORS) - 1)]
        body.append(line + "\n", style=f"bold {color}")

    tagline = Text("sovereign personal ai · local first · no leash\n", style="#c77dff")
    meta = Text()
    if version:
        meta.append(f"v{version}", style="dim #9d00ff")
    if model:
        meta.append(f"  ·  model {model}", style="dim")
    if device:
        meta.append(f"  ·  {device}", style="dim")
    if meta.plain:
        meta.append("\n")

    console.print()
    console.print(body)
    console.print(tagline)
    if meta.plain:
        console.print(meta)
    console.print("[dim]type /help for commands · /exit to leave[/]\n")
