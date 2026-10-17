"""Count usable CI failure samples per repository before any labelling.

For each repository it lists pull-request workflow runs in a date window and counts:
- failed runs (latest attempt failed);
- fail -> fix pairs: a failed run followed by a successful run of the same workflow on the same head
  repository and branch with a different commit, so the diff between the two commits is the fix;
- rerun passes: successful runs with run_attempt > 1, i.e. the same commit failed and then passed
  (candidate flaky or infrastructure failures);
- whether the failed log of one sample run can still be downloaded.

The runs API returns at most 1000 runs per query, so busy repositories may be cut short; `oldest` shows
how far back the fetched runs reach.

    python scripts/feasibility.py --since 2026-07-19 --until 2026-10-17 > data/feasibility.json
"""
import argparse
import collections
import json
import subprocess
import sys

REPOS = [
    # Go
    "prometheus/prometheus", "cli/cli", "etcd-io/etcd", "hashicorp/terraform", "grafana/grafana",
    # Python
    "openai/openai-agents-python", "pydantic/pydantic", "fastapi/fastapi", "pandas-dev/pandas",
    "langchain-ai/langchain",
    # TypeScript / JavaScript
    "vitejs/vite", "withastro/astro", "biomejs/biome",
    # Rust
    "astral-sh/uv", "astral-sh/ruff", "tokio-rs/tokio",
    # Java
    "spring-projects/spring-boot", "apache/kafka",
]


def gh(path: str) -> dict:
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def runs(repo: str, status: str, since: str, until: str) -> list[dict]:
    collected = []
    for page in range(1, 11):
        data = gh(f"repos/{repo}/actions/runs?event=pull_request&status={status}"
                  f"&created={since}..{until}&per_page=100&page={page}")
        batch = data["workflow_runs"]
        collected += batch
        if len(batch) < 100:
            break
    return collected


def key(run: dict) -> tuple:
    head_repo = (run.get("head_repository") or {}).get("full_name")
    return run["workflow_id"], head_repo, run["head_branch"]


def log_available(repo: str, run_id: int) -> bool:
    result = subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo, "--log-failed"],
                            capture_output=True, text=True)
    return result.returncode == 0 and len(result.stdout) > 0


def survey(repo: str, since: str, until: str) -> dict:
    failed = runs(repo, "failure", since, until)
    passed = runs(repo, "success", since, until)
    successes = collections.defaultdict(list)
    for run in passed:
        successes[key(run)].append(run)
    pairs = []
    for run in failed:
        later = [s for s in successes[key(run)]
                 if s["created_at"] > run["created_at"] and s["head_sha"] != run["head_sha"]]
        if later:
            fix = min(later, key=lambda s: s["created_at"])
            pairs.append((run, fix))
    reruns = [run for run in passed if run["run_attempt"] > 1]
    by_workflow = collections.Counter(run["name"] for run, _ in pairs)
    sample = pairs[0][0]["id"] if pairs else None
    return {
        "repo": repo,
        "failedRuns": len(failed),
        "failFixPairs": len(pairs),
        "pairsDistinctBranches": len({key(run) for run, _ in pairs}),
        "rerunPasses": len(reruns),
        "oldestFailed": min((r["created_at"] for r in failed), default=None),
        "failedCapped": len(failed) >= 1000,
        "topWorkflows": by_workflow.most_common(4),
        "sampleLogAvailable": log_available(repo, sample) if sample else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--repos", nargs="*", default=REPOS)
    args = parser.parse_args()
    for repo in args.repos:
        try:
            row = survey(repo, args.since, args.until)
        except RuntimeError as error:
            row = {"repo": repo, "error": str(error)[:200]}
        print(json.dumps(row), flush=True)
        print(repo, "done", file=sys.stderr)


if __name__ == "__main__":
    main()
