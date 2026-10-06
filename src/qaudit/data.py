from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np

from .common import config_at, digest, read_json, stable_order, write_json


def normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def canonical_row(row, dataset):
    labels, choices = list(row["choices"]["label"]), list(row["choices"]["text"])
    if len(labels) != len(choices) or len(set(labels)) != len(labels) or not 2 <= len(choices) <= 26:
        raise ValueError(f"Invalid choices: {row['id']}")
    answer = str(row["answerKey"])
    if answer not in labels:
        raise ValueError(f"Answer key missing: {row['id']}")
    fingerprint = digest([normalize(row["question"]), sorted(normalize(x) for x in choices)])
    return {"key": f"{dataset}:{row['id']}", "id": row["id"], "dataset": dataset,
            "question": row["question"], "choices": choices, "original_labels": labels,
            "gold": labels.index(answer), "content_hash": fingerprint}


def build_splits(raw, cfg):
    """Deduplicate globally, preserving test over validation over training.

    Answer order is ignored for detecting duplicate content. Dataset-qualified
    IDs are used because source IDs may recur across ARC configurations.
    """
    seen_ids, seen_content, exclusions = set(), set(), []
    cleaned = {d: {s: [] for s in ("train", "validation", "test")} for d in cfg["datasets"]}
    for split in ("test", "validation", "train"):
        for dataset in cfg["datasets"]:
            for row in sorted(raw[dataset][split], key=lambda x: str(x["id"])):
                r = canonical_row(row, dataset)
                reason = "duplicate_id" if r["key"] in seen_ids else "duplicate_content" if r["content_hash"] in seen_content else None
                if reason:
                    exclusions.append({"key": r["key"], "split": split, "reason": reason})
                    continue
                seen_ids.add(r["key"])
                seen_content.add(r["content_hash"])
                cleaned[dataset][split].append(r)
    result = {}
    counts = cfg["counts"]
    for dataset, splits in cleaned.items():
        train = stable_order(splits["train"], cfg["seed"], "train-selection")
        if len(train) < counts["pilot"] + counts["calibration"] or len(splits["validation"]) < counts["validation"]:
            raise ValueError(f"Insufficient unique data for {dataset}")
        test = sorted(splits["test"], key=lambda x: x["key"])
        result[dataset] = {
            "pilot": train[:counts["pilot"]],
            "calibration": train[counts["pilot"]:counts["pilot"] + counts["calibration"]],
            "validation": stable_order(splits["validation"], cfg["seed"], "validation")[:counts["validation"]],
            "test": test,
            "robustness": stable_order(test, cfg["seed"], "robustness")[:counts["robustness"]],
        }
    return result, exclusions


def prepare(workspace, config_path):
    from datasets import load_dataset
    from huggingface_hub import HfApi

    ws = Path(workspace)
    cfg = read_json(config_path)
    write_json(ws / "study.json", cfg, immutable=True)
    pins_path = ws / "pins.json"
    if pins_path.exists():
        pins = read_json(pins_path)
    else:
        api = HfApi()
        pins = {"dataset": {"repo": cfg["dataset_repo"], "revision": api.dataset_info(cfg["dataset_repo"]).sha},
                "models": {role: {"repo": repo, "revision": api.model_info(repo).sha} for role, repo in cfg["models"].items()}}
        write_json(pins_path, pins, immutable=True)
    raw = {}
    for dataset in cfg["datasets"]:
        ds = load_dataset(pins["dataset"]["repo"], dataset, revision=pins["dataset"]["revision"])
        raw[dataset] = {s: list(ds[s]) for s in ("train", "validation", "test")}
    splits, exclusions = build_splits(raw, cfg)
    write_json(ws / "splits.json", splits, immutable=True)
    manifest = {"config_hash": digest(cfg), "pins_hash": digest(pins), "splits_hash": digest(splits),
                "counts": {d: {s: len(rows) for s, rows in stages.items()} for d, stages in splits.items()},
                "ids": {d: {s: [r["key"] for r in rows] for s, rows in stages.items()} for d, stages in splits.items()},
                "exclusions": exclusions}
    write_json(ws / "split-manifest.json", manifest, immutable=True)
    return manifest


def selection(workspace, dataset, stage):
    return read_json(Path(workspace) / "splits.json")[dataset][stage]


def permute(row, seed):
    r = dict(row)
    rng = np.random.default_rng(int(digest([seed, row["key"], "option-permutation"])[:16], 16))
    order = rng.permutation(len(row["choices"])).tolist()
    if order == list(range(len(order))):
        order = order[1:] + order[:1]
    r["choices"] = [row["choices"][i] for i in order]
    r["original_labels"] = [row["original_labels"][i] for i in order]
    r["gold"] = order.index(row["gold"])
    r["option_order"] = order
    return r
