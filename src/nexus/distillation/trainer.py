"""QLoRA trainer via Unsloth.

This module is imported lazily — Unsloth + bitsandbytes + torch are heavy. Install with:

    pip install -e '.[training]'
    pip install unsloth  # (install from their latest wheel/repo per their docs)

Runs a single nightly pass on the Qwen 2.5 7B (or 14B) base model. On an RTX 4090
expect ~15-45 minutes for 500-5000 example dataset at rank 32.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.config import settings
from nexus.distillation.teacher import GoldPair

logger = logging.getLogger(__name__)


@dataclass
class TrainConfig:
    base_model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
    rank: int = 32
    alpha: int = 64
    lr: float = 2e-4
    epochs: int = 1
    batch_size: int = 4
    grad_accum: int = 4
    max_seq_len: int = 4096
    rehearsal_ratio: float = 0.10  # 10% of old gold mixed in every run


def _build_dataset(
    gold_pairs: list[GoldPair], rehearsal: list[dict] | None = None
) -> list[dict]:
    ds: list[dict] = []
    for gp in gold_pairs:
        ds.append(
            {
                "messages": [
                    {"role": "user", "content": gp.prompt},
                    {"role": "assistant", "content": gp.teacher_response},
                ]
            }
        )
    ds.extend(rehearsal or [])
    return ds


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def train_qlora(
    gold_pairs: list[GoldPair],
    *,
    config: TrainConfig | None = None,
    output_dir: Path | None = None,
    rehearsal: list[dict] | None = None,
) -> Path:
    """Train a LoRA adapter via Unsloth.

    Returns the output directory (containing adapter_model.safetensors).
    """
    cfg = config or TrainConfig()
    out = output_dir or (settings.oracle_home / "lora" / "pending")
    out.mkdir(parents=True, exist_ok=True)

    if len(gold_pairs) < 10:
        raise RuntimeError(f"too few gold pairs ({len(gold_pairs)}); skipping train")

    dataset = _build_dataset(gold_pairs, rehearsal=rehearsal)
    _write_jsonl(out / "dataset.jsonl", dataset)

    try:
        # Lazy import — training deps are optional
        from unsloth import FastLanguageModel  # type: ignore
        from unsloth.chat_templates import standardize_sharegpt  # type: ignore
        from datasets import Dataset  # type: ignore
        from trl import SFTTrainer, SFTConfig  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Training dependencies not installed. Run: pip install -e '.[training]'"
            " and also `pip install unsloth` per unsloth.ai docs.\n"
            f"missing: {e}"
        )

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=cfg.base_model,
        max_seq_length=cfg.max_seq_len,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=cfg.rank,
        lora_alpha=cfg.alpha,
        lora_dropout=0.05,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    ds = standardize_sharegpt(Dataset.from_list(dataset))

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        args=SFTConfig(
            output_dir=str(out),
            per_device_train_batch_size=cfg.batch_size,
            gradient_accumulation_steps=cfg.grad_accum,
            num_train_epochs=cfg.epochs,
            learning_rate=cfg.lr,
            warmup_ratio=0.03,
            logging_steps=10,
            save_strategy="epoch",
            bf16=True,
            max_seq_length=cfg.max_seq_len,
        ),
    )
    trainer.train()
    model.save_pretrained(str(out))
    tokenizer.save_pretrained(str(out))

    (out / "manifest.json").write_text(
        json.dumps(
            {
                "base_model": cfg.base_model,
                "rank": cfg.rank,
                "alpha": cfg.alpha,
                "gold_pairs": len(gold_pairs),
                "rehearsal_rows": len(rehearsal or []),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out
