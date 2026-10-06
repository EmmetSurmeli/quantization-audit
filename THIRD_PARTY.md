# Data, models, and research attribution

The repository's MIT license applies to the project code and original documentation. It does not replace third-party licenses.

- ARC questions and answers come from [AllenAI's AI2 ARC dataset](https://huggingface.co/datasets/allenai/ai2_arc), distributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The portable archive's `splits.json`, selected question excerpts, and derived question/option representations retain that license. Changes comprise deterministic split selection, duplicate exclusion, canonical option mapping, and the explicitly recorded option permutations. Source revision and question IDs are preserved.
- Model weights originate from the official [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) and [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B) repositories. No model weights are distributed in this Git repository. Consult the pinned upstream model repositories for their licenses and terms.
- [MLX](https://github.com/ml-explore/mlx) and [MLX-LM](https://github.com/ml-explore/mlx-lm) supply model execution and quantization. This project does not claim their implementation as original work.
- Methodological and literature references are linked in `docs/LITERATURE.md` and the technical report.

Implementation and report preparation were AI-assisted. The numerical results are obtained from real model scoring, not generated or synthetic demonstration results.
