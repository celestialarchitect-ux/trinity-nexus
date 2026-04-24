"""SkillRegistry — discovers, persists stats for, and serves skills."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

from oracle.config import settings
from oracle.skills.base import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self, skills_root: Path | None = None):
        base = Path(__file__).parent
        # Scan both seed (shipped) and evolved (self-written) directories.
        self.roots: list[Path] = (
            [skills_root] if skills_root else [base / "seed", base / "evolved"]
        )
        self.stats_file = settings.oracle_home / "skills" / "stats.json"
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        self.skills: dict[str, Skill] = {}

    def load_all(self) -> int:
        self.skills.clear()
        for root in self.roots:
            if not root.exists():
                continue
            for py in sorted(root.rglob("*.py")):
                if py.name.startswith("_"):
                    continue
                try:
                    self._load_file(py)
                except Exception as e:
                    logger.warning("skill load failed for %s: %s", py, e)
        self._load_stats()
        return len(self.skills)

    def _load_file(self, path: Path) -> None:
        mod_name = f"oracle_skill_{path.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if not spec or not spec.loader:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)

        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Skill) and obj is not Skill:
                instance = obj()
                if not instance.id:
                    continue
                if instance.id in self.skills:
                    logger.warning("duplicate skill id: %s", instance.id)
                    continue
                self.skills[instance.id] = instance

    def _load_stats(self) -> None:
        if not self.stats_file.exists():
            return
        try:
            data = json.loads(self.stats_file.read_text(encoding="utf-8"))
            for sid, row in data.items():
                if sid in self.skills:
                    s = self.skills[sid]
                    s.confidence = row.get("confidence", s.confidence)
                    s.usage_count = row.get("usage_count", 0)
                    s.success_count = row.get("success_count", 0)
                    s.failure_count = row.get("failure_count", 0)
                    s.last_used_ts = row.get("last_used_ts", 0.0)
                    s.origin = row.get("origin", "seed")
        except Exception:
            logger.exception("failed to load skill stats")

    def save_stats(self) -> None:
        data = {sid: s.to_stats() for sid, s in self.skills.items()}
        self.stats_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, skill_id: str) -> Skill | None:
        return self.skills.get(skill_id)

    def all(self) -> Iterable[Skill]:
        return self.skills.values()

    def count(self) -> int:
        return len(self.skills)

    def stats(self) -> dict:
        return {
            "total": len(self.skills),
            "by_origin": {
                "seed": sum(1 for s in self.skills.values() if s.origin == "seed"),
                "self_written": sum(
                    1 for s in self.skills.values() if s.origin == "self_written"
                ),
                "mesh": sum(1 for s in self.skills.values() if s.origin == "mesh"),
            },
            "avg_confidence": round(
                sum(s.confidence for s in self.skills.values())
                / max(1, len(self.skills)),
                3,
            ),
        }
