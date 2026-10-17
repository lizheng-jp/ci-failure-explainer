"""Replace each sample's failed log with complete per-job logs from the jobs API.

`gh run view --log-failed` cuts long job logs short: for some pandas test jobs it stopped at the pytest header
and dropped the failures and the `##[error]` line. Here every failed job of the sampled attempt is downloaded
with `GET /actions/jobs/{id}/logs`, which returns the whole log, and written in the same
`job<TAB>step<TAB>line` layout as before. The earlier file is kept as `failed_gh.log`.

    python scripts/joblogs.py
"""
import json
import subprocess
from pathlib import Path

SAMPLES = Path("data/samples")


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:200])
    return result.stdout


def failed_jobs(meta: dict) -> list[dict]:
    attempt = "attempts/1/jobs" if meta["kind"] == "rerun" else "jobs?filter=latest"
    path = f"repos/{meta['repo']}/actions/runs/{meta['failedRun']}/{attempt}"
    jobs = json.loads(gh("api", path + ("&" if "?" in path else "?") + "per_page=100"))["jobs"]
    return [job for job in jobs if job["conclusion"] == "failure"]


def main() -> None:
    for line in open("data/manifest.jsonl"):
        meta = json.loads(line)
        folder = SAMPLES / meta["id"]
        if (folder / "failed_gh.log").exists():
            continue
        jobs = failed_jobs(meta)
        parts = []
        for job in jobs:
            log = gh("api", f"repos/{meta['repo']}/actions/jobs/{job['id']}/logs", "--allow-escape-sequences")
            parts += [f"{job['name']}\tUNKNOWN STEP\t{text}" for text in log.splitlines()]
        if not parts:
            print(meta["id"], "no failed jobs found; kept the old log", flush=True)
            continue
        (folder / "failed.log").rename(folder / "failed_gh.log")
        (folder / "failed.log").write_text("\n".join(parts) + "\n")
        stored = json.loads((folder / "meta.json").read_text())
        stored.update({"failedJobs": len(jobs), "logBytes": sum(len(p) + 1 for p in parts)})
        (folder / "meta.json").write_text(json.dumps(stored, indent=1))
        print(meta["id"], len(jobs), "jobs", stored["logBytes"] // 1000, "KB", flush=True)


if __name__ == "__main__":
    main()
