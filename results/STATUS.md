# Execution status

Complete: both models, all three precisions, both ARC subsets, calibration-size sensitivity checks, and the paired option-permutation check.

- 30,888 actual scoring records across 60 completed cells; 2,670,786 input-token evaluations.
- 19 software tests pass; all 472 acceptance checks pass on the completed archive and on its restored copy.
- The portable archive restores without model weights. Reanalysis reproduces all numerical result fields exactly; rendering and analysis-source metadata may change as presentation code is revised.
- Four principal figures, supporting tables, the six-page technical report, and 20 prespecified case reviews are in [measured](measured/).
- Primary transferred-minus-refitted Brier difference: 0.001749; 95% paired bootstrap interval [-0.003897, 0.008282]. The interval lies inside the prespecified ±0.01 margin, supporting little practical difference for this setup.
- Summed recorded scoring latency: 4,538 seconds (1.26 hours). This is not total project or wall-clock runtime: loading, warm-up, repeatability passes, tokenization, conversion, and analysis are excluded.
- Additional spending: $0. No paid cloud resources were used.

The data-only [protocol amendment](../docs/PROTOCOL-AMENDMENT.md) tightened cross-split stem checks after scoring began but before any held-out performance review. It excluded 20 source rows in total and preserved both complete official test splits. Calibration was refitted and frozen anew. There are 11,340 reused unchanged records, each with validated original provenance.

The corrected pretest artifacts are in `pretest/`; the original freeze is retained in `pretest-v1/`. The final [reproducibility archive](reproducibility/) includes the migration ledgers and all saved scores, without large model weights. Claims and their source tables are indexed in the [claim audit](measured/CLAIM-AUDIT.md).
