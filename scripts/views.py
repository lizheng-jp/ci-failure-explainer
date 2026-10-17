"""Build a condensed labelling view per sample (annotation/INSTRUCTIONS.md describes what labellers see).

The full failed log is often hundreds of kilobytes, mostly runner setup and passing output, and matrix jobs
repeat the same error. The view keeps, per job: every `##[error]` line, the lines leading up to the last
error, and other error-looking lines; jobs whose errors are identical are listed once. The author's fix is
appended, capped in size. Labellers can still open the full files.

    python scripts/views.py
"""
import json
import re
import subprocess
from pathlib import Path

SAMPLES = Path("data/samples")
TIMESTAMP = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
ANSI = re.compile(r"(\x1b|\^\[)\[[0-9;]*[A-Za-z]")  # gh prints ESC as a literal "^["
ERRORISH = re.compile(r"(##\[error\]|\berror\b|\bfailed\b|\bfailure\b|\bFAIL\b|panicked|exception|traceback|"
                      r"assert|timed out|not found)", re.IGNORECASE)
WARNISH = re.compile(r"\bWARNING\b|\bWarning:|treated as errors")
NOT_ERROR = re.compile(r"\b0 (failed|errors?)\b|--fail|failure_error|error_on|errors=0", re.IGNORECASE)
# Passing-test reports whose test names happen to contain "error" or "assert" (nextest, cargo test, pytest, go).
PASSED = re.compile(r"^\s*PASS \[|\.\.\. ok$|\bPASSED\b|^ok\s+\S|^\S+ [.sxX]+\s*\[\s*\d+%\]$")
STEP_TAIL = 50
MAX_JOBS = 3
MAX_GREP = 25
MAX_FIX = 5000


def jobs(log: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in log.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        text = ANSI.sub("", TIMESTAMP.sub("", parts[2])).rstrip()
        out.setdefault(parts[0], []).append(text)
    return out


NOISE = re.compile(r"^(DEBUG |\s*INFO |Received \d+ of \d+|##\[(end)?group\]$|##\[endgroup\]|##\[(start|end)-action)")


def failing_step(lines: list[str]) -> tuple[str, list[str]]:
    """The output of the step that raised the first ##[error]: from its '##[group]Run' header to the error."""
    errors = [i for i, text in enumerate(lines) if "##[error]" in text]
    if not errors:
        return "(no ##[error] line; showing the end of the job)", lines[-STEP_TAIL:]
    first = errors[0]
    starts = [i for i in range(first) if lines[i].startswith("##[group]Run ")]
    begin = starts[-1] if starts else max(0, first - 400)
    header = lines[begin][len("##[group]"):] if starts else "(step header not found)"
    return header, lines[begin + 1:errors[-1] + 1]


def job_view(lines: list[str]) -> tuple[str, str]:
    """The failing step: its command, error-looking lines in it, and its last lines."""
    header, step = failing_step(lines)
    step = [text for text in step if not NOISE.search(text)]
    hits, seen = [], set()
    for text in step:
        if (ERRORISH.search(text) or WARNISH.search(text)) and not NOT_ERROR.search(text) and not PASSED.search(text) \
                and text not in seen:
            seen.add(text)
            hits.append(text[:300])
    chunks = [f"-- failing step: {header[:200]}"]
    if hits:
        chunks.append(f"-- error-looking lines in the step ({min(len(hits), MAX_GREP)} of {len(hits)}) --")
        chunks += hits[-MAX_GREP:]
    chunks.append(f"-- last {STEP_TAIL} lines of the step --")
    chunks += [text[:300] for text in step[-STEP_TAIL:]]
    # Jobs of one matrix fail the same way; compare their hit lines with numbers and paths blurred.
    signature = header + "\n" + "\n".join(sorted({re.sub(r"[\d.]+|/\S+|\\\S+", "#", h) for h in hits[-8:]}))
    return signature, "\n".join(chunks)


def pr_title(meta: dict) -> str:
    if "prTitle" not in meta:
        result = subprocess.run(["gh", "api", f"repos/{meta['repo']}/pulls/{meta['pr']}", "--jq", ".title"],
                                capture_output=True, text=True)
        meta["prTitle"] = result.stdout.strip()
    return meta["prTitle"]


def main() -> None:
    order = []
    for line in open("data/manifest.jsonl"):
        sample_id = json.loads(line)["id"]
        folder = SAMPLES / sample_id
        meta = json.loads((folder / "meta.json").read_text())
        title = pr_title(meta)
        (folder / "meta.json").write_text(json.dumps(meta, indent=1))
        groups: dict[str, list[str]] = {}
        bodies: dict[str, str] = {}
        for name, lines in jobs((folder / "failed.log").read_text(errors="replace")).items():
            signature, body = job_view(lines)
            groups.setdefault(signature, []).append(name)
            bodies.setdefault(signature, body)
        out = [f"id: {sample_id}", f"kind: {meta['kind']}", f"repository: {meta['repo']}",
               f"workflow: {meta['workflow']}", f"PR #{meta['pr']}: {title}", f"run: {meta['url']}", ""]
        for shown_jobs, (signature, names) in enumerate(groups.items()):
            if shown_jobs == MAX_JOBS:
                rest = [name for other in list(groups.values())[MAX_JOBS:] for name in other]
                out.append(f"===== {len(rest)} more failed jobs not shown: {', '.join(rest[:20])}")
                break
            out.append(f"===== failed job: {names[0]}" + (f"  (same errors in: {', '.join(names[1:])})" if names[1:] else ""))
            out.append(bodies[signature])
            out.append("")
        if meta["kind"] == "fail_fix":
            files = json.loads((folder / "fix_files.json").read_text())
            fix = (folder / "fix_pr.diff").read_text()
            out.append(f"===== author's fix: {len(files)} files changed" + ("" if files else " (empty: the base branch changed, not the PR)"))
            out += files[:40]
            out.append("")
            out.append(fix[:MAX_FIX] + (f"\n... (truncated, {len(fix)} bytes; see fix_pr.diff)" if len(fix) > MAX_FIX else ""))
        (folder / "view.txt").write_text("\n".join(out) + "\n")
        order.append((meta["split"], sample_id, len("\n".join(out))))
    for split, sample_id, size in order:
        print(split, sample_id, size)


if __name__ == "__main__":
    main()
