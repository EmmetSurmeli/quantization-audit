# Quantization and confidence

A controlled audit of whether confidence calibration transfers from an unquantized language model to its 8-bit and 4-bit versions.

**Research question:** Does refitting one scalar temperature on 50–400 labeled examples improve held-out probability estimates over reusing the BF16 model's temperature?

This is an applied replication and extension, not a new quantization algorithm. It evaluates **closed-choice probability quality**, not open-ended reasoning or hallucination rates. Temperature scaling does not improve answer accuracy because it preserves the highest-scoring option.

## Study

- Primary: Qwen3-4B / ARC-Challenge / 4-bit / 400 calibration examples.
- Replication: Qwen3-1.7B and ARC-Easy, subject to the runtime gate.
- Intervention: MLX affine weight quantization, group size 64, identical source checkpoint and backend.
- Treatments: raw, transferred BF16 temperature, refitted temperature, and a uniform-probability reference.
- Primary endpoint: transferred minus refitted multiclass Brier score; positive favors refitting.
- Uncertainty: paired question bootstrap, independently resampling calibration and test sets and refitting temperatures in every replicate.
- Practical threshold: 0.01 absolute Brier score, on the sum-of-squares definition (range 0–2).
- Scope: two related ARC subsets and at most two sizes from one model family. No claim of universal calibration transfer.

See [the protocol](docs/PROTOCOL.md), [research context](docs/LITERATURE.md), and [interview guide](docs/OWNERSHIP.md). The execution status and measured outputs, when available, are in [results](results/STATUS.md).

## Install

Apple Silicon with a GPU-accessible macOS session is required for scoring. Statistical analysis and tests do not need MLX or a GPU. Python 3.11+ is supported; the implementation was validated with Python 3.13.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mlx,dev]'
python -m pytest -q
```

Use `requirements-lock.txt` to reproduce the versions used for this execution, if present. Checkpoints and datasets are pinned to immutable Hugging Face revisions during preparation. Model weights are not committed.

The supplied lock targets the measured Apple Silicon/Python 3.13.5 environment. On Linux, install `.[dev]` for CPU-only analysis and tests. If a managed macOS session hides the editable-install path file, run commands with `PYTHONPATH=src python -m qaudit` instead of the `qaudit` entry point.

## Run the primary study

Commands below use `workspaces/main` by default. Supply `--workspace /absolute/path` before the subcommand to store large artifacts elsewhere. Every command maintains an exclusive workspace lock.

```sh
qaudit prepare --config configs/study.json
qaudit convert --role primary
qaudit score --role primary --stage pilot
qaudit gate
```

Read the gate before continuing. It must pass repeatability, prompt consistency, memory, task-performance, and runtime checks. A favorable calibration result is not a gate requirement.

```sh
qaudit score --role primary --stage calibration
qaudit score --role primary --stage validation
qaudit calibrate --role primary
qaudit freeze
qaudit score --role primary --stage test
qaudit score --role primary --stage robustness
qaudit analyze --out results/measured
```

For the two-model study, before freezing: convert the replication model, score its pilot/calibration/validation splits, run `qaudit gate --role replication`, and run `qaudit calibrate --role replication`. Use `qaudit freeze --replication`, then score test/robustness for both roles. The two-model runtime projection must remain within 24 hours.

No command starts a paid service or publishes anything. Default additional spending is $0. A failed gate means stop and revise the scope; there is no automatic backend substitution.

`python scripts/run_study.py --workspace workspaces/main --config configs/study.json --out results/measured --replication --stop-before-test` prepares both models through validation. Omit `--stop-before-test` to continue through the frozen held-out evaluation. It records phase timings, stops on a failed gate, and loads one model at a time.

## Resume and provenance

```sh
qaudit status
qaudit score --role primary --bits 4 --stage pilot --limit 10
```

Scoring saves each question transactionally in SQLite. Rerunning skips completed questions; incomplete cells cannot be analyzed as complete. A changed configuration, prompt/scoring source, pinned input, or scoring environment is rejected when resuming an existing cell. Start a new workspace for a new experiment. Incomplete model conversions are retained for inspection and must be moved aside explicitly before retrying.

Artifacts include immutable split manifests, checkpoint revisions, model file hashes and module inventories, token hashes, option mappings, raw scores, actual token counts, synchronized latency, MLX peak allocation, fitted temperatures, and a frozen protocol. The fitted calibration is hashed before test access. Outputs can be regenerated without model inference.

Cold model loading and warm-up are excluded from per-question latency; the pilot forecast includes a 25% allowance. MLX peak memory is an allocation measurement, not total system memory or energy usage. Do not equate disk reduction with speedup.

## Outputs and claim discipline

To move the score archive to another machine without weights:

```sh
qaudit export --out results/reproducibility
qaudit --workspace workspaces/reanalysis restore --archive results/reproducibility
qaudit --workspace workspaces/reanalysis analyze --out results/reanalysis
```

The archive verifies file checksums before restoration. Reanalysis verifies frozen data and calibration, and records its own software environment; it does not require the original Mac or MLX installation. Resume scoring still requires an exact match to the frozen scoring environment.

`analyze` produces machine-readable results, CSV tables, four PNG figures, stratified error cases, and a Markdown report. Bootstrap confidence intervals incorporate calibration-fit uncertainty. Ten calibration subsets are sensitivity checks, not independent test sets. At 400 examples they coincide and are evaluated once.

The code contains no synthetic production/demo backend. Artificial data appears only in tests and is never a research result. Report both null and positive findings. Claims of accuracy improvement from scalar temperature scaling are invalid.

The data remains subject to the ARC dataset's license and model weights to the Qwen model license. Retain source attribution when distributing study artifacts.
