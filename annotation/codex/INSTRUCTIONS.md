# CI failure labelling task

You label why each CI run failed. Work only from the files in this folder. Do not browse the web or open
GitHub.

## Files per sample

Each sample has a folder `samples/<id>/`:

- `view.txt`: a condensed view made for labelling: repository, workflow, PR title, the failed jobs and steps,
  log lines that look like errors (with context), the last lines of each failed step, and the author's fix.
  Start here; it is enough for most samples.
- `failed.log`: the complete failed log, for when the view is not enough. It can be large; search it.
- `fix_pr.diff` and `fix_files.json` (fail-to-fix samples only): what the PR author changed between the
  failed run and the next successful run. It is computed from the PR's own changes, so commits pulled in by a
  rebase onto the base branch are excluded. `fix_files.json` can be empty: then the author changed nothing and
  the run passed because the base branch changed.
- `fix.diff` (fail-to-fix samples only): the raw diff between the two commits, including any rebase. Use it
  only when `fix_pr.diff` is empty.

`view.txt` states the sample kind:
- `fail_fix`: a failed run, later followed by a successful run on a different commit of the same branch.
- `rerun`: the same commit failed, then passed when re-run.

## What to decide

### 1. `category`: exactly one of

| Category | Use when |
|---|---|
| `code_defect` | A build or test failure that the fix resolves by changing non-test source code (tests may change too). |
| `test_issue` | The fix changes only test code, test data, snapshots or expected output: the test was wrong or out of date. |
| `dependency_env` | Dependency versions, lockfiles, toolchain or runtime versions, or an upstream package change caused it. |
| `static_check` | A lint, format, type-check, spell-check or documentation-build check failed and the fix satisfies it. |
| `ci_config` | The CI workflow, CI scripts or build configuration was wrong (not a dependency version). |
| `flaky_infra` | The failure is not caused by the change: a flaky test, network, timeout, runner, rate limit or service outage. |
| `undeterminable` | You cannot tell the cause from the log and the fix. |

Rules for borderline cases:

1. **Rerun samples are `flaky_infra`** by definition: the same commit passed when re-run. Use `undeterminable`
   only if the log is empty or unreadable.
2. **Label the error the log shows**, not everything the fix touches. If the fix changes several kinds of
   files, choose the category of the change that resolves the logged error.
3. **Source plus tests** changed: `code_defect`. **Only tests** changed: `test_issue`. Updating a snapshot or
   expected output because behaviour changed on purpose is `test_issue`.
4. **A failing static check is `static_check`** even if the fix edits source files to satisfy it (for
   example reformatting `src/x.py`).
5. **Empty `fix_files.json`** (the base branch changed, not the PR): decide from the log what broke. A broken
   dependency or toolchain is `dependency_env`; a broken workflow on the base branch is `ci_config`; a test
   that was flaky on the base branch is `flaky_infra`. If the log does not show which, `undeterminable`.
6. Use `undeterminable` when the logged error is cut off or missing, or the fix is too large or unrelated to
   say which change resolved the error. Do not guess.

### 2. `files`: the files that fix this failure

Only for `code_defect`, `test_issue`, `static_check` and `ci_config`: the files in `fix_files.json` whose
change resolves the logged error. Leave out files changed for other reasons in the same push. Use paths
exactly as written in `fix_files.json`. For the other categories, and when `fix_files.json` is empty, use `[]`.

### 3. `reason`: one short sentence

Name the error and the change that fixed it, for example "test_parse_duration expected 30s; fix corrects the
unit conversion in config/parse.go".

## Output

Write `codex_labels.jsonl` in this folder: one JSON object per line, one line for every id in `samples.txt`, in that order:

```json
{"id": "pydantic-35248454086", "category": "code_defect", "files": ["pydantic/main.py"], "reason": "one short sentence"}
```
