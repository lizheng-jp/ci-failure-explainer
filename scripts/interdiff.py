"""Isolate the author's fix when the branch was rebased or merged with main between failure and fix.

`fix.diff` compares the failed commit with the fixed commit directly, so a rebase in between pulls in every
upstream commit. Here each commit is compared with the PR's base branch instead (three-dot compare uses the
merge base), which gives the PR's own changes at failure time and after the fix. Files whose PR patch
changed between the two are what the author changed to fix the run; `fix_pr.diff` shows, for each such file,
a unified diff of the old PR patch against the new one.

    python scripts/interdiff.py        # every fail -> fix sample in data/manifest.jsonl
"""
import difflib
import json
import subprocess
from pathlib import Path

SAMPLES = Path("data/samples")


def pr_patches(repo: str, base: str, sha: str) -> dict[str, str]:
    result = subprocess.run(["gh", "api", f"repos/{repo}/compare/{base}...{sha}"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:200])
    return {f["filename"]: f.get("patch", f"(no textual patch: {f['status']})")
            for f in json.loads(result.stdout).get("files", [])}


def base_ref(repo: str, pr: int) -> str:
    result = subprocess.run(["gh", "api", f"repos/{repo}/pulls/{pr}", "--jq", ".base.ref"],
                            capture_output=True, text=True)
    return result.stdout.strip() or "main"


def main() -> None:
    for line in open("data/manifest.jsonl"):
        meta = json.loads(line)
        folder = SAMPLES / meta["id"]
        if meta["kind"] != "fail_fix" or (folder / "fix_pr.diff").exists():
            continue
        base = base_ref(meta["repo"], meta["pr"])
        before = pr_patches(meta["repo"], base, meta["failedSha"])
        after = pr_patches(meta["repo"], base, meta["fixedSha"])
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        parts = []
        for name in changed:
            old = before.get(name, "(file not changed by the PR at failure time)").splitlines()
            new = after.get(name, "(file no longer changed by the PR after the fix)").splitlines()
            parts.append(f"=== {name}\n" + "\n".join(difflib.unified_diff(
                old, new, "PR patch at failure", "PR patch after fix", lineterm="", n=2)))
        (folder / "fix_pr.diff").write_text("\n\n".join(parts) + "\n")
        (folder / "fix_files.json").write_text(json.dumps(changed, indent=1))
        meta_file = folder / "meta.json"
        stored = json.loads(meta_file.read_text())
        stored.update({"baseRef": base, "fixFiles": len(changed), "fixPrDiffBytes": sum(map(len, parts))})
        meta_file.write_text(json.dumps(stored, indent=1))
        print(meta["id"], len(changed), "files", flush=True)


if __name__ == "__main__":
    main()
