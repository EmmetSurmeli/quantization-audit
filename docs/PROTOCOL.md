# Prespecified protocol

The canonical machine-readable settings are `configs/study.json`. Changes create a new experiment rather than silently revising a completed run.

## Primary estimand

On Qwen3-4B, ARC-Challenge, and 4-bit MLX affine quantization, compare test Brier score after applying the BF16-fitted temperature with test Brier score after fitting a new temperature to the same 400 training question IDs. The difference is transferred minus refitted; positive values favor refitting. Fit temperatures by minimizing negative log-likelihood, not by optimizing the test metric.

Report a practically meaningful positive point estimate only when the paired 95% interval is positive and the point estimate is at least 0.01. If the entire interval lies within ±0.01, report little practical difference in this setup. Other outcomes are negative or inconclusive; crossing zero does not prove equivalence.

The sum-of-squares multiclass Brier definition is used, without dividing by the number of options. Questions may have different numbers of choices. Padded choices have probability zero. The uniform baseline assigns 1/K to each available choice; its deterministic tie-breaking accuracy is not a meaningful model comparison.

## Data boundary

Deduplicate normalized question and unordered choice content globally across both ARC subsets, with test taking precedence over validation and training. Also exclude repeated normalized question stems across these official splits even when choices differ, and check dataset-qualified source IDs. Record exclusions. Within the same official split, distinct choice sets may share a generic stem. Deterministically choose 100 training questions for the pilot, a disjoint 400-question training calibration pool, and 100 validation questions. Preserve complete test splits unless exact duplicate removal requires an exclusion. The stem rule was added by the documented [protocol amendment](PROTOCOL-AMENDMENT.md), before any held-out performance summary was inspected.

Tokenize the fixed prompt with the pinned official chat template and `enable_thinking=False`. Verify each option letter is exactly one token, save the full prompt-token hash, score the next-token logits once, and normalize over valid letters. Record probability mass outside the choice set. Do not generate reasoning traces, truncate questions silently, or use labels in scoring.

## Pilot and stopping

Score 100 questions per ARC subset at BF16, 8-bit, and 4-bit. Repeat the first three questions of every cell to check numeric repeatability (probability tolerance 0.0001). Require identical prompt hashes, token labels, and option mappings across precisions. Peak MLX allocation must stay below 18 GB, leaving system headroom on the 24 GB Mac.

The BF16 ARC-Challenge pilot accuracy must exceed average random-choice accuracy by 0.05 and stay below 0.98. This is a coarse task/implementation sanity check, not a significance test. Finite scores, correct mappings, and completion of every expected question are required. A calibration improvement is not required.

Estimate total scoring time using each precision/dataset's pilot time and actual split sizes, multiplied by 1.25. Stop if the primary model alone exceeds 24 hours. Admit replication only if the conservative two-model estimate stays within 24 hours. These constraints do not permit changing quantizers or buying compute automatically.

## Calibration and statistics

Fit temperatures separately for each model, precision, and dataset over [0.05,20]. Flag boundary solutions. The transferred temperature always comes from the same model's BF16 variant and same calibration question IDs.

For 50/100/200 examples, use ten seeded nested subsets of the same 400-example pool. At 400 all subsets coincide, so retain one estimate. Report subset variability as such, not as repeated independent experiments.

Primary uncertainty uses 2,000 bootstrap replicates: sample calibration question IDs with replacement; use identical indices for BF16 and 4-bit; refit both temperatures; separately sample test question IDs; evaluate both treatments on those same test indices. Quantization and model checkpoints are fixed, not independently retrained units.

Secondary outputs include NLL, accuracy, prediction transitions, 10-bin ECE, reliability diagrams, and coverage/error at fixed thresholds 0.5/0.7/0.9. Wilson intervals accompany selective error rates; cells with fewer than 50 answered questions are flagged. Secondary findings are exploratory and no multiple-comparison significance claims are made.

## Robustness and error analysis

Select 200 test questions per subset by a fixed hash and apply one deterministic nonidentity permutation. Remap the gold answer and record the original-to-permuted option order. Compare against those same original questions. Permutations are paired observations, never additional sample size. The comparison is descriptive.

Select up to five cases from each primary-test category by a fixed hash: unchanged-correct, unchanged-wrong, beneficial flip, harmful flip. Do not substitute cases if a category has fewer than five. Inspect the actual question, scores, and mappings before interpreting failures.

## Interpretation limits

Temperature scaling changes probabilities but preserves the predicted option. Brier and NLL measure probability quality, not solely calibration. Agreement with BF16 is not ground truth. ARC contamination is unresolved. Two model sizes share a family; the two ARC subsets are not independent domains. No claim about free-form hallucination, general reasoning, other quantizers, or universal deployment safety is licensed by this study.
