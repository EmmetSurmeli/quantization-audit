# Explaining the project

Before using this project in an interview, be able to answer these questions in your own words.

1. **What changed?** Weight precision changes; checkpoint, prompts, backend, task, and option scoring remain controlled.
2. **What is the baseline?** Reusing the temperature fitted to BF16, not merely leaving the quantized model uncalibrated.
3. **What is held out?** Calibration temperatures use training examples. Test questions measure performance after the protocol is frozen.
4. **What is calibration?** Probabilities should agree with observed correctness frequencies. A model can select the same answers while reporting better probabilities.
5. **Why not claim better accuracy?** Dividing all option logits by a positive scalar cannot change which one is largest.
6. **What is the independent observation?** A question, not every precision, calibration subset, or option permutation of that question.
7. **What does the interval include?** Uncertainty from which calibration questions were used and which test questions were evaluated, with pairing retained.
8. **What does the study not show?** Universal equivalence, free-form hallucination reduction, or a result for every quantization method.

AI assistance can handle implementation. Ownership requires understanding the experimental choices, checking key examples, and defending the bounded conclusion. Describe assistance accurately if asked.

Do not fill in a résumé improvement percentage before seeing the held-out result. If an improvement is supported, state the exact metric and baseline, absolute values, sample size, and scope. If it is not, describe the reproducible audit and its measured tradeoffs rather than manufacturing a performance claim.
