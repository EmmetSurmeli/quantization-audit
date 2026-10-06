# Execution status

Checkpoint 1: implementation and pre-test preparation complete. No held-out test results have been inspected.

- 18 automated checks pass, including metric toy cases, label mapping, paired IDs, immutable records, archive restoration, and a complete artificial-data plumbing rehearsal. Artificial fixtures are never reported as findings.
- Both real model pilots passed. The primary-model forecast is 0.705 hours of scoring, or 1.411 hours conservatively for both models, including the 25% allowance. Downloads, conversion, report work, and host overhead are separate.
- Both models have completed 400 calibration and 100 validation questions per dataset at BF16, 8-bit, and 4-bit precision.
- The BF16 primary pilot uses 8.195 GB peak MLX allocation; 4-bit uses 2.609 GB. Quantized scoring was slower in this short-prompt pilot.
- Actual additional spending: $0.

The next checkpoint freezes calibration and protocol before held-out scoring. Full measured results, four figures, and the six-page report will follow.
