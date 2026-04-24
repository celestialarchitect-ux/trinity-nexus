"""Trinity Nexus startup banner — Claude-Code style.

Layout:

  <NEXUS big pixel-block, neon purple gradient>

    Trinity Intelligence Network            (green)

    /help for commands  ·  /exit to leave   (dim)
    cwd:    <current working directory>     (dim)
    model:  <primary>  ·  instance  <name>  (dim)
    v<ver>                                  (dim)

Falls back to a single plain-text line on non-terminal output so piping to
a file keeps working.
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

NEON_PURPLE = [
    "#c77dff",
    "#b23bf2",
    "#9d00ff",
    "#7b00e0",
    "#6a00c2",
    "#5a00a8",
]

ACCENT = "#c77dff"  # neon purple top of the gradient


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

    # Logo — purple gradient
    logo = Text()
    for i, line in enumerate(lines):
        color = NEON_PURPLE[min(i, len(NEON_PURPLE) - 1)]
        logo.append("  " + line + "\n", style=f"bold {color}")

    # Network line — neon purple
    network = Text()
    network.append("  Trinity Intelligence Network\n", style=f"bold {ACCENT}")

    # Help + shortcuts hint
    help_line = Text()
    help_line.append("  /help", style=f"bold {ACCENT}")
    help_line.append(" commands  ·  ", style="dim")
    help_line.append("?", style=f"bold {ACCENT}")
    help_line.append(" shortcuts  ·  ", style="dim")
    help_line.append("/exit", style=f"bold {ACCENT}")
    help_line.append(" to leave\n", style="dim")

    # Cwd + model + instance
    info = Text()
    info.append(f"  cwd:      ", style="dim")
    info.append(f"{os.getcwd()}\n", style=f"{ACCENT}")
    if model:
        info.append(f"  model:    ", style="dim")
        info.append(f"{model}", style=f"{ACCENT}")
        if instance:
            info.append(f"   ·   instance  ", style="dim")
            info.append(f"{instance}", style=f"{ACCENT}")
        info.append("\n")
    if version:
        info.append(f"  v{version}", style="dim")
        if device:
            info.append(f"   ·   {device}", style="dim")
        info.append("\n")

    console.print()
    console.print(logo)
    console.print(network)
    console.print(help_line)
    console.print(info)
