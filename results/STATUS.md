# Execution status

Checkpoint 4: corrected two-model protocol and calibration frozen before resuming held-out scoring.

- 19 automated checks pass, including the changed-distractor leakage regression.
- Both pilots pass; corrected calibration pools retain 400 examples per task.
- The initial combined-content duplicate rule missed four shared stems. The data-only correction, made before held-out performance review, is documented in [the protocol amendment](../docs/PROTOCOL-AMENDMENT.md).
- Current artifacts are in `pretest/`; the original freeze is retained in `pretest-v1/`.
- Both complete test splits are unchanged. Existing raw scores are reused only after exact input and implementation checks, with per-record provenance.
- Additional spending: $0.

Held-out scoring and final analysis are ongoing. No treatment-effect conclusion is claimed yet.
