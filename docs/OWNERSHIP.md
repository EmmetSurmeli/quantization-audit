# Explaining the project

Before using this project in an interview, be able to answer these questions in your own words.

1. **What changed?** Weight precision changes; checkpoint, prompts, backend, task, and option scoring remain controlled.
2. **What is the baseline?** Reusing the temperature fitted to BF16, not merely leaving the quantized model uncalibrated.
3. **What is held out?** Calibration temperatures use training examples; test labels are used for evaluation, never temperature fitting. An initial protocol freeze preceded test scoring. A documented data-only overlap correction preceded all held-out performance review, and calibration was refitted and frozen anew; unchanged raw scores were retained with provenance.
4. **What is calibration?** Probabilities should agree with observed correctness frequencies. A model can select the same answers while reporting better probabilities.
5. **Why not claim better accuracy?** Dividing all option logits by a positive scalar cannot change which one is largest.
6. **What is the independent observation?** A question, not every precision, calibration subset, or option permutation of that question.
7. **What does the interval include?** Uncertainty from which calibration questions were used and which test questions were evaluated, with pairing retained.
8. **What does the study not show?** Universal equivalence, free-form hallucination reduction, or a result for every quantization method.

AI assistance can handle implementation. Ownership requires understanding the experimental choices, checking key examples, and defending the bounded conclusion. Describe assistance accurately if asked.

## Explain the measured result

“I built an audit to test whether calibration survives model compression. The baseline reused the BF16 model's temperature; the intervention refitted a single temperature after quantization. Across 1,172 held-out ARC-Challenge questions, using 400 calibration examples, refitting improved Brier by 0.00175. The paired bootstrap interval was -0.00390 to 0.00828, inside our prespecified ±0.01 practical margin. That supports little practical difference in this setup. It does not prove transfer works for every model or task.”

Be ready to explain why the interval includes both calibration-set and test-set sampling. Reusing fixed fitted temperatures inside every bootstrap would omit calibration-fit uncertainty. Also explain why ten overlapping calibration subsets are sensitivity checks, not ten independent replications.

The deployment tradeoff is separate: 4-bit Qwen3-4B used 2.275 GB of serialized storage versus 8.056 GB for BF16, while Challenge accuracy dropped 2.73 percentage points and scoring was slower in this run. Do not turn a storage reduction into a speed claim, or an ECE reduction into an accuracy claim.

A defensible résumé description after you can explain the work: “Built an AI-assisted, reproducible MLX quantization audit spanning 30,888 scoring records across two Qwen3 models; implemented calibration-transfer evaluation, paired bootstrap uncertainty, immutable provenance, and weight-free result reproduction.” Describe your own implementation and review contributions accurately.

The next research question is whether this narrow transfer result survives a preregistered replication on a different model family and a task outside ARC, keeping the endpoint and practical margin fixed. See the [claim audit](../results/measured/CLAIM-AUDIT.md) for evidence and boundaries.
