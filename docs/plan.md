# Plan: diagnosing CI failure causes

> English translation of the pre-registered plan. The plan was written and committed before any data was
> collected; sections 3, 5, 6, 7, 8 and 11 were frozen at that point, and every later change is logged in
> section 12 with its date and reason. Results are in [report.en.md](report.en.md).

---

## 1. The question

**When CI fails, can an AI read the log, name the right cause category, point at the file to change, and say
"unsure" when it cannot tell? Is it clearly better than what a few rules can do?**

Motivation: supporting error analysis of CI/CD pipelines and deployment configuration with an AI workflow, a
typical platform-engineering / AI-enablement task.

## 2. What the system does

**Input**: the failed log of a failed CI run (originally `gh run view --log-failed`; see section 12), and the
list of files the pull request changes.
**Not visible**: the later fix commit.

**Output** (JSON):

| Field | Content |
|---|---|
| `category` | one of the 6 classes in section 5, or `unsure` |
| `confidence` | `high` or `low` |
| `evidence` | log lines supporting the answer (verbatim) |
| `files` | the files most likely to need a change, at most 3, most likely first |
| `explanation` | one or two sentences |

## 3. Data

### Repositories and time window

Window: 2026-07-19 to 2026-10-17 (the last 90 days). Feasibility survey (`data/feasibility.jsonl`,
2026-10-17):

| Repository | Language | Usable PR branches (fail -> fix) | Passed on rerun | Use |
|---|---|---|---|---|
| pandas-dev/pandas | Python | 61 | 16 | dev |
| tokio-rs/tokio | Rust | 52 | 14 | dev |
| spring-projects/spring-boot | Java | 42 | 88 | dev |
| prometheus/prometheus | Go | 59 | 17 | test |
| pydantic/pydantic | Python | 73 | 18 | test |
| vitejs/vite | TypeScript | 74 | 41 | test |
| astral-sh/uv | Rust | 113 | 138 | test |
| apache/kafka | Java | 88 | 481 | test |

- **Dev set** (3 repositories): used only to write prompts and rules.
- **Test set** (5 repositories): used only to compute the final numbers. No system runs on the test set before
  prompts and rules are final.
- The test set includes Go and TypeScript, which the dev set lacks, to check generalisation to unseen
  languages.

### What counts as a sample

**Fail -> fix sample**: on one workflow and one PR branch, a failure followed by a success on a different
commit. Take **the last failure before the fix**; the diff between it and the successful commit is the fix.

**Rerun sample**: the same commit failed on its first run and passed on rerun. Take the first attempt's log
(`--attempt 1`).

### Sampling

- **At most 1 sample per PR branch**: repeated failures of one PR are highly similar and must not be counted
  twice.
- Per repository: 15 fail -> fix samples + up to 4 rerun samples, drawn at random with seed `20261017`.
- About 150 in total: about 57 dev, about 95 test.
- **The class mix is set by the sampling design** and does not represent the real-world distribution, so the
  main metric is macro-F1, which does not depend on class proportions, and every class is reported separately.

### Excluded workflows

Only workflows that build, test, lint or type-check code are kept. Workflows whose name contains any of these
(case-insensitive) are excluded: `title`, `release note`, `label`, `review`, `cla`, `codeql`, `scorecard`,
`codspeed`, `benchmark`, `autofix`, `dependabot`, `copilot`, `stale`, `triage`.

Why: failures such as PR-title checks are too easy for rules and would make the rules baseline look too strong;
security scans and benchmarks fail for different reasons.

### Save all raw data first

Logs expire after 90 days. Right after sampling, **all failed logs, fix diffs and PR file lists are downloaded**;
everything afterwards uses the local copies.

## 4. Labels

Two labels per sample. Annotators see: the failed log, the fix diff, and the PR title.

**Cause category** (section 5), plus:
- `undeterminable`: the cause cannot be told even from the log and the fix, for example because the fix diff is
  a merge of the main branch touching dozens of files. These samples are **not scored**, but their number is
  reported.

**Relevant files**: the files in the fix diff that actually address this failure (unrelated changes excluded).
Labelled only for code defect, test issue, static check and CI configuration.

### Labelling process

1. Claude labels a first pass.
2. Codex labels blind: shuffled order, the same written rules, without seeing the first pass.
3. Compute kappa on the category, adjudicate disagreements by the written rules, and document the reasons.
4. **After the user reviews the adjudication, labels are committed to git, and only then does any system under
   test run.**

## 5. Cause categories (6)

| Category | Criterion |
|---|---|
| `code_defect` | a test or build fails and the fix changes source code |
| `test_issue` | the fix changes test code: a wrong test, an outdated assertion, a snapshot to update |
| `dependency_env` | version conflicts, lockfiles, toolchain versions, upstream package changes |
| `static_check` | lint, formatting, type checking, spell checking |
| `ci_config` | a wrong workflow file, build script or CI configuration |
| `flaky_infra` | the same commit passes on rerun; network, timeouts, runners, rate limits |

## 6. Systems under test: the ablation ladder

Each rung adds exactly one change to the rung before. The order is fixed here and not changed after seeing
results.

| Rung | Configuration | Question it answers |
|---|---|---|
| 0 | majority: always the dev set's most common category | what no thinking scores |
| 1 | rules: classify by failing step name and log keywords (for example `lint` in the step name, `ETIMEDOUT` in the log), written on the dev set only | how far a few lines of code get. **The AI must clearly beat this** |
| 2 | LLM reads the last N lines of the failed log | the simplest AI approach |
| 3 | + log cleaning: strip timestamps and colour codes, fold repeated lines | does denoising help |
| 4 | + in-log retrieval: chunk the whole log, retrieve the k most relevant chunks with bge-base instead of the tail | does retrieval help |
| 5 | + the PR's changed-file list | does knowing what the PR changed improve diagnosis and localisation |
| 6 | + few-shot examples chosen from the dev set | do examples help |
| 7 (optional) | + a stronger (Pro) model | is the extra cost worth it; estimate the cost on dev first and skip it if over budget |

- Model: rungs 2 to 6 use `gemini-3.8-flash` at temperature 0.
- **Final system**: from rung 2 on, a rung's change is **kept in the final system only if it raises dev
  macro-F1**; otherwise the final system skips it (the ladder chart still shows the rung). The final system is
  what section 8 tests; it is fixed and committed to git at the end of the dev phase.
- On the test set, every rung and the final system run once. This describes each component's contribution; it
  is not choosing the best configuration on the test set.

### Tuning range (dev set only)

| Parameter | Rung | Candidates |
|---|---|---|
| tail lines N | 2 | 100 / 200 / 400 |
| chunk size | 4 | 20 / 40 lines |
| retrieved chunks k | 4 | 4 / 8 |
| retrieval query | 4 | a fixed sentence ("error failure cause") / the failing step name + lines containing "error" |
| number of examples | 6 | 3 / 6 |
| thinking level | 2-6 | low / medium |
| prompt | 2-6 | at most 3 versions |

Every parameter not in this table is fixed. Each rung chooses its own parameters in order before moving on.

## 7. Metrics and figures

All computed on the **test set**, excluding `undeterminable` samples.

| Metric | Note |
|---|---|
| category macro-F1 | main metric, with a bootstrap 95% confidence interval |
| category accuracy | secondary |
| per-class precision and recall | which classes go wrong |
| high-confidence precision and coverage | among `confidence: high` answers only: how accurate, and what share of all samples |
| file hit@1 / @3 | whether a labelled relevant file is among the first 1 / 3 files given; only the four classes with file labels |
| cost and latency per sample | |

**Adjacent rungs, and the final system against rung 1, are compared with a paired bootstrap**: resample the same
samples and compute the confidence interval of the macro-F1 difference.

Three figures in the report:
1. **Ablation ladder**: rungs 0 to 7 on the x axis, macro-F1 on the y axis, **each bar with a 95% CI error
   bar**. A rung that drops is drawn as it is.
2. **Precision vs coverage**: add samples from most to least confident and show how accuracy changes.
3. **Confusion matrix**: the final system across the 6 classes.

## 8. Success criteria (fixed in advance)

"Final system" below is the system chosen by the rule in section 6.

| Condition | Target |
|---|---|
| 1. Better than rules | the final system's macro-F1 is **>= 0.10** above rung 1 (rules), and the paired difference's 95% CI lower bound is **> 0** |
| 2. Accurate when confident | on `confidence: high` samples the final system's accuracy is **>= 0.80**, and they are **>= 50%** of all samples |
| 3. Points at files | the final system's file hit@1 is **>= 0.50** |

- **All three met**: the conclusion is "on this data, AI diagnosis is practically useful".
- **Any one not met**: report which one honestly. For example, if only 1 fails, the conclusion is "not
  significantly better than rules".
- The conclusion goes into the report whichever way it falls.

On sample size: with about 95 test samples the macro-F1 confidence interval is roughly ±0.08. Differences of a
few points between adjacent rungs mostly cannot be told from noise, and the report says so.

## 9. Optional: external check (only if time allows)

Test rung 4's retrieval on [LogChunks](https://zenodo.org/records/3632351), which marks "the part that explains
the failure" in 797 Travis CI logs. Only "can the right part be retrieved" is tested; results are exploratory
and do not affect section 8. (Not done.)

## 10. Deliverables

1. Dataset: sample list, labels, labelling records (logs stay local and are not committed, to avoid
   redistributing large amounts of third-party logs)
2. Evaluation report with the three figures of section 7
3. A reusable workflow `ci-failure-explainer` that comments on the PR when CI fails, demonstrated on our own
   repository. **It does not affect the conclusions of section 8 and is built after the evaluation.**

## 11. Cost control, steps and stopping rule

### Cost control

- **All model calls use the Gemini Batch API** (half the normal price, results within 24 hours). Each dev tuning
  round packs its parameter combinations into one batch; the whole test ladder is one batch.
- **Before every batch, a smoke test**:
  1. take 3 of the requests about to be submitted and run them as normal calls (under one cent)
  2. check that the requests succeed, the answers parse as the JSON of section 2, every field is present, and
     the scoring script can compute the metrics
  3. count the whole batch's input tokens with Gemini's (free) token-count endpoint and estimate the cost
  4. submit only when all of this passes and the estimate fits the remaining budget
- After each batch, record the actual tokens and cost in `runs/cost.jsonl`.
- **Budget cap US$30.** If spending so far plus the next batch's estimate exceeds it, do not submit; write the
  report from the results available.

### Steps and checkpoints

| Step | Content | Checkpoint |
|---|---|---|
| 1 | sample, download all raw data (logs, fix diffs, PR file lists) | report the sample count |
| 2 | write the labelling rules, Claude labels the first pass | - |
| 3 | Codex labels blind, compute agreement | - |
| 4 | adjudicate disagreements | **user review**, then freeze labels and commit |
| 5 | tune rung by rung on dev (at most 3 batch rounds), fix the final system | commit rules, prompts, parameters and the final system |
| 6 | run the whole ladder on the test set once (1 batch) | - |
| 7 | compute metrics, draw figures, conclude by section 8, write the report | **user reads the report** |
| 8 | build the reusable workflow and demonstrate it | - |

After each step, wait for the user at a checkpoint; steps without one go straight on.

### Stopping rule

Stop when the numbers of section 7 exist, the section 8 conclusion is drawn and the report is written. No new
systems, no new data.

## 12. Deviations from the plan

- **146 samples, not about 150** (step 1, 2026-10-17): spring-boot yielded 0 rerun samples and kafka only 2. In
  these two repositories almost all "reruns" were first-time contributors' runs waiting for maintainer approval
  (first attempt `action_required`), not real failures followed by reruns (kafka 264, spring-boot 38). By the
  sampling rule they never counted as rerun samples, so none were drawn instead. Final: dev 53 (45 fail -> fix,
  8 rerun), test 93 (75, 18).
- **Added "the author's own fix", `fix_pr.diff`** (step 1): in 34 of the 120 fail -> fix samples `fix.diff` was
  over 100 KB, because the author rebased or merged the main branch between failure and fix, pulling hundreds
  of unrelated upstream commits into the diff. Instead, the failed and the fixed commit are each compared with
  the PR's base branch, and the files whose PR changes differ between the two are the author's fix (median 2
  files). The raw `fix.diff` is kept. In 14 samples the PR's own changes did not differ at all, meaning the fix
  came from an update of the main branch, not from the author; these are labelled by their actual cause. This
  only changes what annotators see, not sampling or the input of the systems under test.
- **Failed logs replaced by complete job logs** (before step 2, 2026-10-17): during labelling it turned out that
  `gh run view --log-failed` truncates long job logs. For one pandas test job the downloaded log stopped at the
  start of pytest and lost 3 `FAILED` lines and the `##[error]` line, which the full log from the jobs API
  (`GET /actions/jobs/{id}/logs`) contains. So for every sample, the complete logs of all failed jobs of the
  sampled run (the first attempt for rerun samples) were re-downloaded to replace `failed.log`; the old file is
  kept as `failed_gh.log`. The systems under test also use the complete logs. No labels existed and no system
  had run yet, and sampling was not affected.
- **A third annotator, Gemini, joined the vote on disagreements** (step 4, 2026-10-17): Claude and Codex
  disagreed on 18 samples (15 on the category, 3 on files only). The user decided to add a blind tie-breaker,
  given only rules 1 to 6 and the sample material, without the other two labels. A batch to
  `gemini-3.1-pro-preview` was submitted first, had not returned after 45 minutes and was cancelled; the user
  then chose the model under test, `gemini-3.8-flash`, run synchronously on the 18 samples (about US$0.1-0.3;
  whether the Pro batch was partly billed before the cancel was unknown, and it later turned out to have
  completed). The final category is the three-way majority; the files are those listed by at least two of the
  annotators who chose that category; where all three differ, the manual adjudication stands. Kafka's three
  draft-gate samples are the same case; the vote made two `undeterminable` and split three ways on the third,
  which was aligned to `undeterminable`.
  - **This favours the model under test on these samples**: for 16 of the 18 the final category equals
    gemini-3.8-flash's own answer, 15 of them in the test set. So it is fixed in advance that step 6 also reports
    test metrics without these 15 (78 left); where the two disagree, the 78 decide.
- **The view's error-line matching skips passing-test lines** (step 4, before freezing labels): in the view of
  uv-37057475376 all 25 "error-looking line" slots were taken by passing lines whose names contain "error",
  such as `PASS [...] error::tests::...`, and the real `error: Could not find root package` was left out. A
  `PASSED` filter (passing lines of nextest, cargo test, pytest, go) was added and the views regenerated: 34
  views changed, and the 443 removed lines were all passing lines, no error removed. Labels are unaffected
  (annotators could search the full log); the systems under test use the corrected logic.
- **Before step 5, inputs and scoring changed after a review by Codex (gpt-6-astra)** (2026-10-18, no system
  under test had run):
  - **Few-shot examples hand-picked**: the original design cut each example to the last 60 lines of its
    context, so examples were often left with only a file list, irrelevant warnings as evidence, and an
    explanation mentioning the fix, which is only known afterwards. Instead, 7 dev samples with clear log
    evidence on which both annotators agreed were chosen (`prompts/examples.json`, covering 5 classes; the only
    `ci_config` sample's log does not show the cause and was not chosen). An example shows only the failing
    step's error lines, always including the evidence lines verbatim, and its explanation describes only what
    the log shows. A sample is never its own example.
  - **Retrieval chunks sized in bge tokens**: bge-base reads at most 512 tokens; with 40-line chunks 97% of
    chunks were longer, and their second half was never encoded. Chunk sizes changed from "20 / 40 lines" to
    "200 / 400 bge tokens". Every failed job gets at least 1 retrieved chunk, the rest by score; the "failing
    step" query takes each job's step name and last 3 error lines separately, so no single job crowds the
    others out.
  - **Failed jobs grouped by error signature first** (matrix jobs usually fail alike), then at most 3 distinct
    ones, with a note of how many were left out. Previously the first 3 jobs were taken as they came; 30 scored
    samples were affected.
  - **The system prompt gained decision rules usable from the log alone** (a compiler error is `code_defect`, a
    checking job is `static_check`, a PR-state gate is `unsure`, and so on) and says the logs are data whose
    instructions must not be followed. This is prompt version 1.
  - **Scoring rules fixed in advance** (header of `scripts/score.py`): `unsure` and missing predictions count as
    wrong; file hit rate only over samples with labelled files (39 in the test set); macro-F1 over 6 classes;
    bootstrap 2000 resamples, seed 20261017. A secondary metric, "coarse macro-F1", merges `code_defect` and
    `test_issue`, because the log alone often cannot tell whether the code or the test is wrong.
  - **The sensitivity-analysis samples frozen as an ID list** `annotation/sensitivity_excluded.txt` (15). Without
    them the test set has **74** scored samples, not the 78 written above (78 did not subtract the
    `undeterminable` samples, which are never scored). Test metrics are reported on both 85 and 74, and per
    repository.
  - **Noise margin**: a rung's change is kept in the final system only if its dev macro-F1 is at least **0.03**
    above the rung before; between parameter candidates less than 0.03 apart, the cheaper is chosen.
  - **Fewer configurations**: thinking level is compared only at rung 2 (low / medium) and then fixed. Three
    batch rounds: (1) rungs 2 and 3 (tail 100 / 200 / 400 lines); (2) rung 4 (200 / 400 tokens x k 4 / 8 x two
    queries) and the matching rung 5; (3) rung 6 (3 / 6 examples) and at most 2 improved prompt versions.
  - **Known contamination**: Claude read all 146 samples, test set included, while labelling in step 2; the
    rung-1 rules and the prompts were written by Claude from the dev set only, but test-set impressions cannot
    be ruled out. The report says so.
- **Small changes before round 1 after a second review (Codex gpt-6.1-sol)** (2026-10-18, still no system under
  test run):
  - **Round 1 selection order** (fixed before results): (1) among rung 2's 6 configurations (tail 100 / 200 /
    400 lines x thinking low / medium) take the highest dev macro-F1; among those within 0.03 of it, the cheapest
    (fewer lines first, then low thinking). (2) Thinking is fixed to that level from then on. (3) Rung 3 picks its
    line count among its 3 configurations at that level by the same rule; log cleaning is kept in the final
    system only if rung 3's best is at least 0.03 above rung 2's choice. (4) Rung 3 at the other thinking level is
    reported as exploratory only. Rung 3 runs at both levels so cleaning can be compared pairwise at the same
    line count and thinking level, about US$1 more than planned.
  - **The macro-F1 denominator depends on the labels only**: the average is over the classes with at least one
    gold sample in the set being scored (all 6 in the full dev and test sets; a bootstrap resample may lack one),
    so two systems compared on the same resample share the denominator.
  - **Runner**: each batch is saved as soon as it is created, so a rerun after a failure never pays twice;
    answers are matched to requests by a key sent with each request and checked for completeness; each batch's
    cost is logged once; submitting is refused when spending so far plus the round's quote would exceed US$30;
    answers are validated field by field and invalid ones count as `unsure`; smoke-test answers go through the
    scorer.
  - **Failing-step boundary**: the failing step ends at its own last error, not at errors of later cleanup steps
    (affects 1 of 224 jobs; job grouping unchanged).
  - **Rules baseline**: file paths are also taken from the lines just before and after an error line. Dev file
    hit@1 rose from 0.24 to 0.27; category metrics unchanged. Then frozen.
  - **Left for before later rounds**: rung 4's per-job queries to be encoded separately (before round 2); the
    example samples being scored at rung 6 gives a slight optimistic bias, so round 3 also reports results
    without those 7 samples.
- **Round 1 results and round 2 selection order** (2026-10-18, written before round 2 was submitted): round 1
  selected tail 200 lines, low thinking, by the rules above; log cleaning did not reach +0.03 and is not in the
  final system (`runs/r1/SELECTION.md`). Round 2:
  - rung 4, 8 configurations (200 / 400 tokens x k 4 / 8 x fixed / failing-step query); rung 5, the same 8 with
    the PR file list; plus one configuration "last 200 raw lines + PR file list"; 17 x 50 requests.
  - (1) Rung 4 takes the highest dev macro-F1; within 0.03, the cheaper (smaller k first, then smaller chunks,
    then the fixed query). (2) Retrieval is kept in the final system only if rung 4's choice is at least 0.03
    above rung 3's choice (0.518). (3) Rung 5 is the rung-4 choice plus the file list; the file list is kept only
    if it is at least 0.03 above rung 4's choice. (4) If retrieval is not kept but the file list is, the final
    system is "last 200 lines + file list"; its dev score is reported but not used in the decisions above.
  - Per-job "failing step" queries are now encoded separately, each job's chunks compared only with its own
    query. Dense retrieval often ranks setup-step output first; that is the effect rung 4 is meant to test, so
    no keyword fallback is added.
- **Deviation: the PR file list added to the final system** (2026-10-18, the user's decision, made after seeing
  results): under the written rules the file list was judged on "retrieval 200 tokens x 4 chunks", which happened
  to be the only one of 9 pairs where it did not help (-0.005), so it was not kept. But on the base the final
  system actually uses, "last 200 lines", adding the file list raised dev macro-F1 from 0.542 to 0.603 (paired
  +0.062, 95% CI [-0.014, 0.157]), and it helped in 8 of the 9 pairs. So the final system was changed to "last
  200 raw lines + PR file list". **This deviation was made after seeing results**: the test set also reports
  the final system under the original rules (rung 2: last 200 lines, 0.542), both are judged against the three
  criteria of section 8, and the report gives the original-rule conclusion first.
- **Round 3 configurations and selection order** (written before round 3 was submitted): 7 x 50 requests, all at
  low thinking.
  - Ladder rung 6: rung 5's choice (retrieval 200 tokens x 4 chunks, fixed query + file list) plus 3 / 6
    examples; the higher one, 3 if within 0.03. Used only for the ladder chart.
  - Examples in the final system: 3 / 6 examples on "last 200 lines + file list" (0.603); kept only if the higher
    one is at least 0.03 above 0.603 (count chosen by the same rule), otherwise no examples.
  - Prompt version 2, written from rounds 1-2 dev errors (`test_issue` recall 0.20, often answered `unsure`;
    flaky failures read as real ones; `unsure` always scored wrong); its text is `PROMPT_V2_RULES` in
    `scripts/inputs.py`. It is adopted only if it is at least 0.03 above version 1 at the example count chosen
    above, so version 2 runs with 0, 3 and 6 examples.
  - The 7 example samples are themselves dev samples, so rung 6 and every with-examples result is also reported
    on the 43 samples without them.
  - After round 3 the final system is frozen and committed, then the test set runs.
- **Rung 7 (Pro model) not run** (2026-10-18, the user's decision): the ladder ends at rung 6.

## 13. Known risks

| Risk | Response |
|---|---|
| fix commits mix in unrelated changes, or the developer simply disabled the failing test | annotators separate "relevant files"; unclear cases are `undeterminable` |
| "passed on rerun" is not always flaky: an external dependency may just have recovered | both go into `flaky_infra`; the category definition already merges them |
| the sampled class mix differs from the real distribution | main metric is macro-F1, every class reported |
| the model saw these repositories in training | logs and fixes are from the last 90 days, so memorised answers are unlikely but cannot be ruled out; stated in the report |
| all annotators are language models | double-blind labelling plus user review of the adjudication; stated in the report |
| logs may contain personal data (user names, paths) | logs are not committed; quotes in the report drop user names |
| generalising to a company's internal CI | cannot be verified: internal plugins and infrastructure are not covered by open-source repositories; stated in the report |
