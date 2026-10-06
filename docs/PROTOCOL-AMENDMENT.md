# Protocol amendment: repeated question stems

The first protocol was frozen and pushed at commit `47177fd`. An additional data-only audit, conducted while held-out scoring was in progress and before any held-out performance summary was computed or inspected, found four normalized question stems shared between calibration and test. Their distractors differed, so the original combined question-and-choice fingerprint did not detect them.

Two examples were clear near-duplicates: the bird/nest observation question (`Mercury_7107380` / `Mercury_406136`) and the Adirondack pollution question (`Mercury_409875` / `Mercury_7172813`). The other shared stems asked about chemical change and good health habits. Model predictions were not used to decide which questions to remove.

## Correction

Version 2 excludes any normalized question stem already present in a higher-priority official split, even when choices differ. Priority remains test, then validation, then train. Within a single official split, distinct questions with different choice sets may retain a generic shared stem. Exact combined-content and dataset-qualified ID deduplication remains in force.

- Across all source records, 16 stem matches and four exact-content duplicates are excluded.
- Both complete test splits are unchanged: 1,172 ARC-Challenge and 2,376 ARC-Easy questions.
- The selected ARC-Challenge pilot replaces one question, and its calibration pool replaces four IDs (including a shift caused by keeping the pilot at 100).
- The ARC-Easy calibration pool replaces one ID. Both selected validation sets are unchanged.
- Each task retains 100 pilot, 400 calibration, 100 validation, and 200 permutation questions.
- The corrected calibration pools have zero raw-ID, combined-content, or normalized-stem overlap with test.

The hypotheses, primary endpoint, bootstrap, practical margin, model revisions, quantization, prompts, tokenization, temperature bounds, and seeds are unchanged. Temperatures are refitted on the corrected pools before resuming held-out evaluation. This is a disclosed protocol amendment, not an untouched preregistration.

## Reusing expensive work transparently

The original workspace is retained. A separate version-2 workspace receives scores only for unchanged questions. The migration verifies that the original Git checkpoint matches the original scoring-source hash and that backend, scoring, statistics, store, environment, model files, and prompt configuration are unchanged. It compares every reused question's full row, including choices and canonical labels. Each reused record stores its original protocol hash, cell, and record hash.

The first three questions of every pilot cell are rescored to verify repeatability after selection changes. New pre-test IDs are scored normally. Calibration artifacts and the corrected protocol are frozen anew. Only then are unchanged raw test scores copied with their original provenance and scoring resumed for missing questions. Existing test model outputs are not recalculated or selected based on their outcomes.

The corrected freeze therefore precedes resumed scoring, but some raw scores were acquired under the initial frozen protocol. This timing is disclosed in the report and archive. No accuracy, Brier, NLL, ECE, or treatment-effect summary on held-out data informed the correction.
