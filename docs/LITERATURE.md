# Research context and contribution boundary

This project is an applied replication and extension. A modern checkpoint or local runtime is not sufficient novelty for a publication claim.

| Prior work | Established result / scope | Relationship to this study |
|---|---|---|
| [Guo et al., ICML 2017](https://proceedings.mlr.press/v70/guo17a.html) | Scalar temperature scaling is an effective simple calibration baseline in studied classification settings. | We reuse the method rather than claim to invent calibration. |
| [Proskurina et al., NAACL Findings 2024](https://aclanthology.org/2024.findings-naacl.124/) | GPTQ 4-bit compression changes confidence in architecture-, scale-, and confidence-dependent ways. | Quantization-induced confidence drift is established; our focus is transfer and labeled refitting cost. |
| [Accuracy Is Not All You Need, 2024](https://arxiv.org/abs/2407.09141) | Similar aggregate accuracy can hide changed predictions and distributional behavior. | Prediction-transition plots are supporting diagnostics, not a new contribution. |
| [Zhong et al., ACL 2025](https://aclanthology.org/2025.acl-long.1473/) | Studies quantized-model calibration and soft-prompt calibration repair using 7–8B models. | Our intervention is a scalar refit with no model training; the scoring pipeline also differs. |
| [Target-Aware Calibration Data Selection, 2026 preprint](https://arxiv.org/abs/2608.21019) | Studies selecting pre-quantization calibration data to preserve full-precision uncertainty behavior. | Preserving BF16 behavior and calibrating against labels are different objectives. |

Our bounded question is whether the temperature fitted before compression remains useful afterward, and whether 50–400 labeled examples justify refitting, using paired uncertainty estimates. The exact combination has not been established as unprecedented.

## Why the initial reasoning-compute project was not selected

The original general question has substantial overlap with [Self-Consistency](https://arxiv.org/abs/2203.11171), [Adaptive-Consistency](https://aclanthology.org/2023.emnlp-main.761/), [compute-optimal test-time scaling](https://arxiv.org/abs/2408.03314), [Learning How Hard to Think](https://proceedings.iclr.cc/paper_files/paper/2025/file/ff414825df833edb8b1839e3d5d495e9-Paper-Conference.pdf), and [AERA](https://arxiv.org/abs/2608.27964). A careful reproduction could be educational but requires many sampled generations and a stronger novelty argument.

The selected project instead concentrates the available time on controlled measurement, reproducibility, and a practical calibration decision. Null results are retained. Publication is a possible later direction, not the completion requirement.
