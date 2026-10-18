# Round 3 selection and the frozen final system (dev, 50 scored samples)

| config | macro-F1 | 43 samples without the 7 examples | note |
|---|---|---|---|
| rung 5: retrieval c200 k4 fixed + files | 0.514 | 0.477 | |
| **rung 6: + 3 examples** | **0.523** | 0.505 | 6 examples: 0.519 |
| **final base: tail 200 + files (v1)** | **0.603** | 0.587 | |
| + 3 examples | 0.605 | 0.608 | paired +0.002 [-0.049, 0.052] |
| + 6 examples | 0.604 | | |
| prompt v2, no examples | 0.589 | | paired -0.014 [-0.102, 0.074] |
| prompt v2 + 3 examples | 0.598 | | |
| prompt v2 + 6 examples | 0.618 | 0.624 | exploratory only, see below |

1. Ladder rung 6: 3 examples (0.523) and 6 (0.519) are within 0.03; **3 examples** for the ladder chart.
2. Final system examples: 0.605 / 0.604 are not 0.03 above 0.603: **no examples.**
3. Prompt v2 at 0 examples (0.589) is not 0.03 above v1 (0.603): **prompt v1 kept.**
4. **Frozen final system: last 200 raw log lines of each distinct failed job (up to 3) + the PR's changed-file
   list, prompt v1, no examples, gemini-3.8-flash, thinking low, temperature 0.** Dev macro-F1 0.603
   [0.51, 0.81], accuracy 0.72, high-confidence precision 0.80 at coverage 0.88, file hit@1 0.55, @3 0.76.
   Versus the rules baseline on dev: +0.099 [-0.049, 0.268] (the rules were revised on dev).
5. The final system under the original rules (plan section 12) stays rung 2: tail 200, low (dev 0.542).

The best dev number, prompt v2 + 6 examples (0.618), is within noise of the frozen system and was not reached
by the written order; it is not used. Round 3 batch cost US$1.86; total spent US$6.98 plus the estimated
US$0.25 Pro tie-break batch.
