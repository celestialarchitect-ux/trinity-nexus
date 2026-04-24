"""AdapterValidator — the eval gate that prevents silent degradation.

Per SLAO + continual-learning research, every nightly adapter must pass:
  1. Regression test set — old held-out Q/A where we know the right answer;
     new adapter must not regress below 95% of baseline score.
  2. Diversity test — varied queries across the user's domains; average quality
     must stay >= 80%.
  3. Improvement test — the exact prompts this adapter was trained to fix;
     must show net improvement > 0.

If any gate fails, the adapter is archived and NOT deployed. The model rolls
back to the previous adapter. This is the anti-drift mechanism.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    adapter_id: str
    regression_pass_rate: float
    diversity_score: float
    improvement_rate: float
    accepted: bool
    rejection_reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class AdapterValidator:
    def __init__(
        self,
        *,
        regression_threshold: float = 0.95,
        diversity_threshold: float = 0.80,
        improvement_threshold: float = 0.0,
    ):
        self.reg_t = regression_threshold
        self.div_t = diversity_threshold
        self.imp_t = improvement_threshold

    def validate(
        self,
        *,
        adapter_path: Path,
        regression_scores: list[float],
        diversity_scores: list[float],
        improvement_scores: list[float],
    ) -> ValidationResult:
        def avg(xs: list[float]) -> float:
            return sum(xs) / max(1, len(xs))

        reg = avg(regression_scores)
        div = avg(diversity_scores)
        imp = avg(improvement_scores)

        reasons: list[str] = []
        if reg < self.reg_t:
            reasons.append(
                f"regression_pass_rate {reg:.2f} < {self.reg_t:.2f}"
            )
        if div < self.div_t:
            reasons.append(f"diversity_score {div:.2f} < {self.div_t:.2f}")
        if imp <= self.imp_t:
            reasons.append(f"improvement_rate {imp:.2f} <= {self.imp_t:.2f}")

        result = ValidationResult(
            adapter_id=adapter_path.name,
            regression_pass_rate=round(reg, 4),
            diversity_score=round(div, 4),
            improvement_rate=round(imp, 4),
            accepted=not reasons,
            rejection_reasons=reasons,
        )

        (adapter_path / "validation.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        return result
