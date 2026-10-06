# Validation review before held-out scoring

Both pilots passed. All calibration temperatures are interior to the fixed [0.05,20] bounds. Each precision used the same prompt-token hashes and option mapping. No test scores existed when this review was written.

| Model | Dataset | Bits | Validation n | Accuracy | Mean outside-choice mass |
|---|---|---:|---:|---:|---:|
| primary | ARC-Challenge | 16 | 100 | 0.800 | 0.0027 |
| primary | ARC-Challenge | 8 | 100 | 0.800 | 0.0050 |
| primary | ARC-Challenge | 4 | 100 | 0.800 | 0.0218 |
| primary | ARC-Easy | 16 | 100 | 0.970 | 0.0030 |
| primary | ARC-Easy | 8 | 100 | 0.970 | 0.0034 |
| primary | ARC-Easy | 4 | 100 | 0.950 | 0.0101 |
| replication | ARC-Challenge | 16 | 100 | 0.650 | 0.1411 |
| replication | ARC-Challenge | 8 | 100 | 0.710 | 0.1602 |
| replication | ARC-Challenge | 4 | 100 | 0.560 | 0.0003 |
| replication | ARC-Easy | 16 | 100 | 0.910 | 0.0990 |
| replication | ARC-Easy | 8 | 100 | 0.900 | 0.1242 |
| replication | ARC-Easy | 4 | 100 | 0.780 | 0.0080 |

The 1.7B 4-bit variant has lower validation accuracy. Retain it as an observed quantization effect, not a reason to select a different checkpoint. Its calibrated scores still use the same predefined pipeline. Higher outside-choice mass in some 1.7B conditions reinforces the closed-choice scope.

Five primary BF16 pilot questions were inspected directly for question text, original option labels, canonical gold index, and model choice. Label mapping agreed; no prompt or scoring change was made after examining validation.

Protocol, revisions, split IDs, and both fitted calibration artifacts are hashed in frozen.json. The upcoming primary comparison remains 4B / ARC-Challenge / 4-bit / n=400, irrespective of the result.
