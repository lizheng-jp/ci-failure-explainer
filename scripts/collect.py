"""Sample CI failures and download everything labelling and evaluation need (plan sections 3 and 11, step 1).

Per repository it draws, with a fixed seed and at most one sample per PR branch:
- fail -> fix samples: the last failed run before a successful run of the same workflow on the same branch
  with a different commit. Downloads the failed log, the fix diff and the PR's changed files.
- rerun samples: a successful run whose first attempt failed on the same commit. Downloads the first
  attempt's failed log and the PR's changed files.

A candidate that cannot be downloaded is skipped and the next one is tried; skips are recorded with their
reason. Nothing is filtered on log or diff content. Re-running resumes: finished samples are kept.

    python scripts/collect.py                    # all repositories
    python scripts/collect.py --repos pydantic/pydantic --pairs 2 --reruns 1   # smoke test
"""
import argparse
import collections
import json
import random
import subprocess
import sys
from pathlib import Path

from feasibility import key, runs

SINCE, UNTIL = "2026-07-19", "2026-10-17"
SEED = 20261017
SPLITS = {
    "pandas-dev/pandas": "dev", "tokio-rs/tokio": "dev", "spring-projects/spring-boot": "dev",
    "prometheus/prometheus": "test", "pydantic/pydantic": "test", "vitejs/vite": "test",
    "astral-sh/uv": "test", "apache/kafka": "test",
}
EXCLUDE = ["title", "release note", "label", "review", "cla", "codeql", "scorecard", "codspeed",
           "benchmark", "autofix", "dependabot", "copilot", "stale", "triage"]
DATA = Path("data")
SAMPLES = DATA / "samples"


def gh(*args: str, accept: str | None = None) -> str:
    command = ["gh", *args]
    if accept:
        command[2:2] = ["-H", f"Accept: {accept}"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:300])
    return result.stdout


def excluded(run: dict) -> bool:
    name = (run.get("name") or "").lower()
    return any(word in name for word in EXCLUDE)


def branch(run: dict) -> tuple:
    return (run.get("head_repository") or {}).get("full_name"), run["head_branch"]


def candidates(repo: str) -> tuple[dict, list]:
    """Fail -> fix pairs grouped by branch, and rerun passes, all outside excluded workflows."""
    failed = [r for r in runs(repo, "failure", SINCE, UNTIL) if not excluded(r)]
    passed = [r for r in runs(repo, "success", SINCE, UNTIL) if not excluded(r)]
    by_key = collections.defaultdict(list)
    for run in failed + passed:
        by_key[key(run)].append(run)
    pairs = collections.defaultdict(list)
    for group in by_key.values():
        group.sort(key=lambda r: r["created_at"])
        for before, after in zip(group, group[1:]):
            # The last failure immediately followed by a success on a different commit.
            if (before["conclusion"] == "failure" and after["conclusion"] == "success"
                    and before["head_sha"] != after["head_sha"]):
                pairs[branch(before)].append((before, after))
    reruns = [r for r in passed if r["run_attempt"] > 1]
    return pairs, reruns


def pr_info(repo: str, sha: str, run: dict) -> tuple[int | None, list[str]]:
    numbers = json.loads(gh("api", f"repos/{repo}/commits/{sha}/pulls"))
    if not numbers:
        # A force-pushed commit is no longer associated with its PR; look the PR up by branch instead.
        head_repo, name = branch(run)
        owner = (head_repo or repo).split("/")[0]
        numbers = json.loads(gh("api", f"repos/{repo}/pulls?head={owner}:{name}&state=all"))
    if not numbers:
        return None, []
    pr = numbers[0]
    compare = json.loads(gh("api", f"repos/{repo}/compare/{pr['base']['ref']}...{sha}"))
    return pr["number"], [f["filename"] for f in compare.get("files", [])]


def download(repo: str, kind: str, failed: dict, fixed: dict | None) -> dict:
    sample_id = f"{repo.split('/')[1]}-{failed['id']}"
    folder = SAMPLES / sample_id
    if (folder / "meta.json").exists():
        return json.loads((folder / "meta.json").read_text())
    attempt = []
    if kind == "rerun":
        first = json.loads(gh("api", f"repos/{repo}/actions/runs/{failed['id']}/attempts/1"))
        if first["conclusion"] != "failure":
            raise RuntimeError(f"first attempt concluded {first['conclusion']}")
        attempt = ["--attempt", "1"]
    log = gh("run", "view", str(failed["id"]), "--repo", repo, "--log-failed", *attempt)
    if not log.strip():
        raise RuntimeError("empty failed log")
    diff = ""
    if fixed:
        diff = gh("api", f"repos/{repo}/compare/{failed['head_sha']}...{fixed['head_sha']}",
                  accept="application/vnd.github.diff")
        if not diff.strip():
            raise RuntimeError("empty fix diff")
    number, files = pr_info(repo, failed["head_sha"], failed)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "failed.log").write_text(log)
    if fixed:
        (folder / "fix.diff").write_text(diff)
    (folder / "pr_files.json").write_text(json.dumps(files, indent=1))
    meta = {
        "id": sample_id, "repo": repo, "split": SPLITS[repo], "kind": kind,
        "workflow": failed["name"], "headRepo": branch(failed)[0], "branch": failed["head_branch"],
        "failedRun": failed["id"], "failedSha": failed["head_sha"], "failedAt": failed["created_at"],
        "fixedRun": fixed["id"] if fixed else None, "fixedSha": fixed["head_sha"] if fixed else None,
        "pr": number, "prFiles": len(files),
        "url": f"https://github.com/{repo}/actions/runs/{failed['id']}" + ("/attempts/1" if attempt else ""),
        "logBytes": len(log), "diffBytes": len(diff),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def collect(repo: str, want_pairs: int, want_reruns: int, rng: random.Random, skips) -> list[dict]:
    pairs, reruns = candidates(repo)
    branches = sorted(pairs, key=str)
    rng.shuffle(branches)
    used, chosen = set(), []
    for name in branches:
        if sum(m["kind"] == "fail_fix" for m in chosen) == want_pairs:
            break
        failed, fixed = rng.choice(pairs[name])
        try:
            chosen.append(download(repo, "fail_fix", failed, fixed))
            used.add(name)
        except RuntimeError as error:
            skips.write(json.dumps({"repo": repo, "run": failed["id"], "reason": str(error)}) + "\n")
    rerun_pool = sorted((r for r in reruns if branch(r) not in used), key=lambda r: r["id"])
    rng.shuffle(rerun_pool)
    for run in rerun_pool:
        if sum(m["kind"] == "rerun" for m in chosen) == want_reruns:
            break
        if branch(run) in used:
            continue
        try:
            chosen.append(download(repo, "rerun", run, None))
            used.add(branch(run))
        except RuntimeError as error:
            skips.write(json.dumps({"repo": repo, "run": run["id"], "reason": str(error)}) + "\n")
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos", nargs="*", default=list(SPLITS))
    parser.add_argument("--pairs", type=int, default=15)
    parser.add_argument("--reruns", type=int, default=4)
    parser.add_argument("--manifest", default=str(DATA / "manifest.jsonl"))
    args = parser.parse_args()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    with open(args.manifest, "w") as manifest, open(DATA / "skips.jsonl", "a") as skips:
        for repo in args.repos:
            # One generator per repository, so a repository's sample does not depend on the others.
            rng = random.Random(f"{SEED}:{repo}")
            chosen = collect(repo, args.pairs, args.reruns, rng, skips)
            for meta in chosen:
                manifest.write(json.dumps(meta) + "\n")
            counts = collections.Counter(m["kind"] for m in chosen)
            print(f"{repo}: {dict(counts)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
