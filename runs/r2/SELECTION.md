# Round 2 selection (dev, 50 scored samples), applying the rules written before the results

| config | macro-F1 | with PR files (rung 5) | gain from files |
|---|---|---|---|
| chunk 200, k 4, fixed | **0.519** (selected rung 4) | 0.514 | -0.005 |
| chunk 200, k 4, step | 0.483 | 0.562 | +0.079 |
| chunk 200, k 8, fixed | 0.531 | 0.534 | +0.003 |
| chunk 200, k 8, step | 0.456 | 0.556 | +0.100 |
| chunk 400, k 4, fixed | 0.449 | 0.530 | +0.081 |
| chunk 400, k 4, step | 0.423 | 0.525 | +0.102 |
| chunk 400, k 8, fixed | 0.504 | 0.549 | +0.045 |
| chunk 400, k 8, step | 0.456 | 0.605 | +0.149 |
| tail 200 raw (round 1 selection) | 0.542 | 0.603 (`x_tail200_files`) | +0.061 |

1. Rung 4: best is chunk 200, k 8, fixed (0.531); within 0.03 are chunk 200 k 4 fixed (0.519) and chunk 400
   k 8 fixed (0.504); the cheapest is k 4. **Selected: chunk 200, k 4, fixed query.**
2. Rung 4 (0.519) is not 0.03 above rung 3 (0.518): **retrieval is not kept.** Paired +0.001 [-0.066, 0.065].
3. Rung 5 = selected rung 4 + PR files = 0.514, not 0.03 above 0.519: **by the written rule, the PR file list
   is not kept.** Paired -0.005 [-0.120, 0.101].
4. So the final system under the written rules stays round 1's: tail 200 raw lines, low thinking (0.542).

Observed but not used by the written rules: adding the file list raised macro-F1 in 8 of the 9 pairs above
(mean about +0.07); the rule happened to test it on the one pair where it did not help. On the system the
final one is actually built on, tail 200 + files scores 0.603 vs 0.542, paired +0.062 [-0.014, 0.157]; vs the
rules baseline +0.099 [-0.049, 0.268]. With files, file hit@3 rises from about 0.6 to 0.76-0.88.
Retrieval was worse than the plain tail in most settings and lowered file hit@1.
Round 2 batch cost US$1.30; total spent US$5.11 plus the estimated US$0.25 Pro tie-break batch.
