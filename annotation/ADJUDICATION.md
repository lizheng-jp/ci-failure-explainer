# Steps 3-4: blind-label agreement and the three-way vote

## Agreement between Claude and Codex

| Metric | Value |
|---|---|
| Samples | 146 (Codex covered all) |
| Same category | 131/146 = 89.7% |
| Cohen's kappa | **0.872** |
| Relevant files (where both gave files) | identical 66/70, overlapping 69/70 |

In 12 of the 15 category disagreements one side chose `undeterminable`; Codex was the more cautious.

## Three-way vote (18 disagreements)

The third blind annotator was `gemini-3.8-flash`, given only rules 1-6 and the sample material, without the
other two labels. Rules:

- **Category**: the one at least two of the three chose.
- **Files**: those listed by at least two of the annotators who chose that category.
- **All three differ**: the manual adjudication stands.

| id | Claude | Codex | Gemini | Final |
|---|---|---|---|---|
| kafka-35963399303 | ci_config | undeterminable | undeterminable | undeterminable |
| kafka-36422964308 | ci_config | undeterminable | undeterminable | undeterminable |
| kafka-37487208730 | ci_config | undeterminable | flaky_infra | undeterminable (three-way split; same case as the two above, aligned) |
| kafka-36323025054 | test_issue | undeterminable | undeterminable | undeterminable |
| pandas-37173593142 | code_defect | code_defect | code_defect | files: datetimelike.py |
| prometheus-37727862532 | code_defect | static_check | code_defect | code_defect |
| prometheus-38161501187 | undeterminable | flaky_infra | flaky_infra | flaky_infra |
| prometheus-38561395622 | code_defect | code_defect | code_defect | files: 3 promtool files + tsdbblockutil.go |
| pydantic-31971978623 | flaky_infra | undeterminable | flaky_infra | flaky_infra |
| pydantic-36081183687 | undeterminable | test_issue | test_issue | test_issue |
| spring-boot-35128514055 | code_defect | test_issue | test_issue | test_issue |
| tokio-38259978008 | code_defect | undeterminable | flaky_infra | code_defect (three-way split, manual adjudication) |
| uv-36783477168 | static_check | code_defect | code_defect | code_defect |
| uv-37057475376 | undeterminable | code_defect | code_defect | code_defect, 5 files |
| uv-38803708458 | static_check | static_check | static_check | files: Cargo.toml added |
| vite-35345381481 | flaky_infra | undeterminable | flaky_infra | flaky_infra |
| vite-35968299449 | flaky_infra | undeterminable | flaky_infra | flaky_infra |
| vite-37899478039 | flaky_infra | undeterminable | flaky_infra | flaky_infra |

Votes and reasons per sample are in `adjudication.jsonl`; the manual adjudication from before the vote is kept
in `adjudication.manual.jsonl`, and the vote changed 9 of its decisions.

## Frozen label distribution

| Category | dev (53) | test (93) |
|---|---|---|
| code_defect | 8 | 6 |
| test_issue | 10 | 13 |
| dependency_env | 7 | 7 |
| static_check | 14 | 20 |
| ci_config | **1** | **2** |
| flaky_infra | 10 | 37 |
| undeterminable | 3 | 8 |

## Caveats

1. **The model under test helped set the labels.** The first two annotators disagreed, so every majority
   includes Gemini. For 16 of the 18 the final category is gemini-3.8-flash's own answer, 15 of them in the test
   set. Plan section 12 therefore requires every test metric also on the set without these 15 (74 scored
   samples remain; the plan first wrote 78 before subtracting unscored samples).
2. **Too few `ci_config` samples.** 1 in dev and 2 in test: that class's F1 means little and makes macro-F1
   jumpy. The report says so.
3. **tokio-38259978008** split three ways and kept the manual adjudication, `code_defect`: HTTP/2 frames go
   through exactly the codec the PR changed. It is the only category decided by Claude alone.
