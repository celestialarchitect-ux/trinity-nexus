"""Claude-Code-style thinking indicator — with spiritual/esoteric verbs.

Shows a pulsing glyph, a rotating esoteric verb, and elapsed time while the
model is working. Swaps the verb every few seconds on long thoughts.

    ✦ Channeling… (6s)

Colors match the ORACLE banner (neon purple). Silently no-ops on non-terminal
output so piped sessions stay clean.
"""

from __future__ import annotations

import itertools
import random
import threading
import time
from contextlib import AbstractContextManager
from typing import Callable

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text


# ---------------------------------------------------------------------------
# Esoteric verb pool — chosen to feel like summoning/channeling, not corporate.
# ---------------------------------------------------------------------------

VERBS: list[str] = [
    "Channeling",
    "Divining",
    "Scrying",
    "Attuning",
    "Communing",
    "Invoking",
    "Manifesting",
    "Ascending",
    "Meditating",
    "Contemplating",
    "Transmuting",
    "Conjuring",
    "Incanting",
    "Awakening",
    "Summoning",
    "Illuminating",
    "Transcending",
    "Revealing",
    "Prophesying",
    "Whispering",
    "Harmonizing",
    "Refracting",
    "Probing",
    "Weaving",
    "Enchanting",
    "Sensing",
    "Aligning",
    "Unveiling",
    "Dissolving",
    "Crystallizing",
    "Piercing",
    "Kindling",
    "Igniting",
    "Grounding",
    "Rising",
    "Dreaming",
    "Envisioning",
    "Perceiving",
    "Receiving",
    "Transmitting",
    "Decoding",
    "Inscribing",
    "Sigiling",
    "Casting",
    "Spiraling",
    "Pulsing",
    "Threading",
    "Fathoming",
    "Sounding",
    "Diving",
    "Questing",
    "Tracking",
    "Heralding",
    "Beseeching",
    "Consecrating",
    "Blessing",
    "Evoking",
    "Listening",
    "Echoing",
    "Resonating",
    "Vibrating",
    "Crystalgazing",
    "Beholding",
    "Kenning",
    "Glimpsing",
    "Alchemizing",
    "Anointing",
    "Auguring",
    "Hallowing",
    "Hermeticizing",
    "Sublimating",
    "Theurgizing",
    "Thaumaturging",
    "Gnosticizing",
    "Dowsing",
    "Hexing",
    "Blessing",
    "Consulting",
    "Orbiting",
    "Crossing",
    "Veiling",
    "Unbinding",
    "Threading",
    "Walking",
    "Dreaming",
    "Shadow-walking",
    "Aether-sifting",
    "Akashic-reading",
    "Ley-tracing",
    "Veil-piercing",
    "Sigil-forging",
    "Rune-casting",
    "Star-charting",
    "Omen-reading",
    "Spirit-hailing",
    "Nexus-weaving",
    "Chakra-aligning",
    "Mantra-spinning",
    "Prana-drawing",
    "Egregore-consulting",
    "Tulpa-shaping",
    "Thoughtform-binding",
    "Oracular-sounding",
]


# Rotating glyphs — mystical/stellar, more esoteric than basic spinners.
GLYPHS: list[str] = [
    "✦",
    "✧",
    "✩",
    "✪",
    "✫",
    "✬",
    "✭",
    "✮",
    "✯",
    "✰",
]


# How often (seconds) the verb switches on a long thought.
VERB_ROTATION_SEC = 5.0

# How often (seconds) the glyph cycles — fast pulse for the "alive" feel.
GLYPH_INTERVAL_SEC = 0.12


class Thinking(AbstractContextManager):
    """Context manager that shows a rotating esoteric spinner.

    Usage:
        with Thinking(console) as t:
            ...  # work
            t.pause()                # hide spinner, safe to print
            console.print("…")       # your output
            t.resume(verb="Receiving")
        # spinner disappears on exit
    """

    def __init__(
        self,
        console: Console,
        *,
        initial_verb: str | None = None,
        color: str = "#b23bf2",
        dim_after_sec: float = 20.0,
    ):
        self.console = console
        self._color = color
        self._initial_verb = initial_verb or random.choice(VERBS)
        self._current_verb = self._initial_verb
        self._glyph_iter = itertools.cycle(GLYPHS)
        self._t0 = 0.0
        self._last_verb_swap = 0.0
        self._dim_after = dim_after_sec
        self._live: Live | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._paused = False
        self._active = console.is_terminal

    # ---------- context manager ----------

    def __enter__(self) -> "Thinking":
        if not self._active:
            return self
        self._t0 = time.time()
        self._last_verb_swap = self._t0
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        self._live.__enter__()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ---------- controls ----------

    def set_verb(self, verb: str) -> None:
        self._current_verb = verb
        self._last_verb_swap = time.time()

    def pause(self) -> None:
        """Hide the spinner so you can print normally. Call resume() to show again."""
        if self._paused or not self._live:
            return
        self._paused = True
        try:
            self._live.stop()
        except Exception:
            pass
        self._live = None

    def resume(self, *, verb: str | None = None) -> None:
        if not self._active or not self._paused:
            return
        if verb:
            self.set_verb(verb)
        self._paused = False
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        self._live.__enter__()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if self._live:
            try:
                self._live.__exit__(None, None, None)
            except Exception:
                pass
            self._live = None

    # ---------- internals ----------

    def _render(self) -> Text:
        glyph = next(self._glyph_iter)
        elapsed = time.time() - self._t0
        secs = int(elapsed)
        label = self._current_verb
        # Claude Code-esque dim-out on very long thoughts
        dim = elapsed > self._dim_after
        text = Text()
        text.append(f" {glyph} ", style=f"bold {self._color}")
        text.append(f"{label}…", style=("dim " if dim else "") + self._color)
        text.append(f"  ({secs}s)", style="dim")
        return text

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(GLYPH_INTERVAL_SEC)
            if self._paused or not self._live:
                continue
            # Periodically swap verb on long thoughts
            if time.time() - self._last_verb_swap > VERB_ROTATION_SEC:
                self._current_verb = random.choice(VERBS)
                self._last_verb_swap = time.time()
            try:
                self._live.update(self._render())
            except Exception:
                # Live may have been stopped by another thread
                break
