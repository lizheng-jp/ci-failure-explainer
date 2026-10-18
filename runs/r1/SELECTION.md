# Round 1 selection (dev, 50 scored samples), applying plan section 12 as written before the results

| config | macro-F1 | 95% CI | accuracy | unsure | high-conf precision / coverage | file@1 |
|---|---|---|---|---|---|---|
| rung 0 majority | 0.073 | 0.05-0.11 | 0.28 | 0 | - / 0.00 | 0.00 |
| rung 1 rules | 0.504 | 0.39-0.70 | 0.62 | 0 | 0.77 / 0.44 | 0.27 |
| r2 tail100 low / medium | 0.446 / 0.446 | | 0.50 / 0.50 | 13 / 13 | | 0.42 / 0.45 |
| **r2 tail200 low** | **0.542** | 0.43-0.73 | 0.66 | 4 | 0.72 / 0.92 | 0.55 |
| r2 tail200 medium | 0.538 | | 0.66 | 4 | 0.71 / 0.84 | 0.55 |
| r2 tail400 low / medium | 0.540 / 0.530 | | 0.66 / 0.64 | 4 / 4 | | 0.52 / 0.55 |
| r3 tail100 low / medium | 0.430 / 0.469 | | 0.48 / 0.52 | 13 / 13 | | 0.42 / 0.42 |
| **r3 tail200 low** | **0.518** | 0.42-0.70 | 0.64 | 4 | 0.69 / 0.90 | 0.55 |
| r3 tail200 medium | 0.515 | | 0.64 | 4 | | 0.55 |
| r3 tail400 low / medium | 0.540 / 0.505 | | 0.66 / 0.62 | 4 / 4 | | 0.52 / 0.48 |

1. Rung 2: best is tail200 low (0.542). tail200 medium, tail400 low and tail400 medium are within 0.03; the
   cheapest of the tied set is tail200 low. **Selected: tail 200, thinking low.**
2. Thinking is fixed to low from here on.
3. Rung 3 at low: best is tail400 (0.540); tail200 (0.518) is within 0.03 and cheaper. **Selected: tail 200.**
4. Rung 3 (0.518) is not at least 0.03 above rung 2 (0.542): **log cleaning is not kept in the final system.**
   Paired difference r3 - r2: -0.024, 95% CI [-0.085, 0.000].

Exploratory: rung 2 minus rules on dev is +0.038, 95% CI [-0.109, 0.191]; the rules were revised on dev, so
this comparison favours them. The model's gains are in file hit@1 (0.55 vs 0.27) and dependency_env; its
losses are test_issue (recall 0.20, 4 unsure) and flaky_infra (recall 0.30; failures that passed on rerun read
like real test or doc-build errors).
Round 1 batch cost US$3.52; total spent US$3.81 plus an estimated US$0.25 for the label tie-break Pro batch.
