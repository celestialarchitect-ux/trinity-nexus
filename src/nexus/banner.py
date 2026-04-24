"""Trinity Nexus banner — retro neon purple on startup.

Solid-block NEXUS with TRINITY NEXUS subtitle. Renders in every modern
monospace font; silently downgrades on non-terminal output.
Switch styles with NEXUS_BANNER=pixel|shadow|off (or ORACLE_BANNER=…).
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.text import Text


PIXEL_NEXUS = [
    "███    ██ ███████ ██   ██ ██    ██ ███████",
    "████   ██ ██       ██ ██  ██    ██ ██     ",
    "██ ██  ██ █████     ███   ██    ██ ███████",
    "██  ██ ██ ██       ██ ██  ██    ██      ██",
    "██   ████ ███████ ██   ██  ██████  ███████",
]

SHADOW_NEXUS = [
    r"███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗",
    r"████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝",
    r"██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗",
    r"██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║",
    r"██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║",
    r"╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝",
]

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
    instance: str = "",
) -> None:
    style = (os.environ.get("NEXUS_BANNER") or os.environ.get("ORACLE_BANNER") or "pixel").lower().strip()
    if style == "off":
        return

    if not console.is_terminal:
        console.print(f"Trinity Nexus v{version} · {model} · {device}")
        return

    lines = SHADOW_NEXUS if style == "shadow" else PIXEL_NEXUS

    body = Text()
    for i, line in enumerate(lines):
        color = NEON_COLORS[min(i, len(NEON_COLORS) - 1)]
        body.append(line + "\n", style=f"bold {color}")

    title = Text("T R I N I T Y   N E X U S\n", style="bold #c77dff")
    tagline = Text(
        "adaptive intelligence · local-first · truth before comfort\n",
        style="#9d00ff",
    )

    meta = Text()
    if instance:
        meta.append(f"instance {instance}", style="dim #c77dff")
    if version:
        meta.append(("  ·  " if meta.plain else "") + f"v{version}", style="dim")
    if model:
        meta.append(f"  ·  {model}", style="dim")
    if device:
        meta.append(f"  ·  {device}", style="dim")
    if meta.plain:
        meta.append("\n")

    console.print()
    console.print(body)
    console.print(title)
    console.print(tagline)
    if meta.plain:
        console.print(meta)
    console.print("[dim]type /help for commands · /exit to leave[/]\n")
