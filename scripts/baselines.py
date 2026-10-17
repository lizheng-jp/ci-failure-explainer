"""Ladder rungs 0 and 1: no model, no cost (plan section 6).

Rung 0 always answers the dev split's most common category. Rung 1 classifies by the failing job and step
names and keywords in the error lines, and names files by pulling paths out of the error lines. The rules were
written from general CI knowledge and the dev split only, revised once on dev (dependency errors before job
names; check tasks named in the log), and frozen once committed.

    python scripts/baselines.py dev      # writes runs/baselines/{r0_majority,r1_rules}.dev.jsonl
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inputs import clean, distinct_jobs, error_lines, labels, scored_ids  # noqa: E402

OUT = Path("runs/baselines")

CHECK_JOB = re.compile(r"lint|fmt|format|clippy|mypy|typing|type.?check|spell|ruff|pre-commit|checkstyle|eslint|"
                       r"prettier|hawk|shear|\bdocs?\b|doc build|docs build|documentation", re.I)
INFRA = re.compile(r"timed out|timeout|ETIMEDOUT|ECONNRESET|ECONNREFUSED|connection (reset|aborted|refused)|"
                   r"RemoteDisconnected|nodename nor servname|could not resolve host|temporary failure in name|"
                   r"\b50[234]\b|rate limit|no space left|The operation was canceled|runner .* lost|"
                   r"exit code 137|killed|failed to download|network", re.I)
DEPENDENCY = re.compile(r"no matching distribution|ResolutionImpossible|version solving failed|could not resolve "
                        r"dependencies|unsatisfiable|requires-python|lock ?file|pnpm-lock|unstable library feature|"
                        r"is not supported by|toolchain|in crate `(libc|std)`|could not compile `(?!{repo})[\w-]+`",
                        re.I)
CHECK_TEXT = re.compile(r"Task :\S*(checkFormat|checkstyle|spotless|lint|format)\S* FAILED|checkstyle violation|"
                        r"would reformat|rustfmt --check|flake8|eslint|ruff check", re.I)
CI_CONFIG = re.compile(r"invalid workflow file|unable to resolve action|actionlint|unrecognized named-value|"
                       r"\.github/workflows/", re.I)
COMPILE = re.compile(r"error\[E\d+\]|error TS\d+|cannot find symbol|compilation failed|COMPILATION ERROR|"
                     r"\bundefined: |could not compile|SyntaxError|build failed", re.I)
TEST_ASSERT = re.compile(r"AssertionError|assert_\w*equal|assertion failed|expected .* (to be|but got)|"
                         r"snapshot|Expected:|Received:|NameError|ImportError|fixture", re.I)
TEST_FAIL = re.compile(r"\bFAILED\b|\bFAIL\b|panicked|Exception|Error:", re.I)
PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:py|pyi|rs|go|java|kt|ts|tsx|js|mjs|yml|yaml|toml|rst|"
                  r"md|json|c|h|cpp))\b")


def rules(sample_id: str) -> dict:
    repo = sample_id.rsplit("-", 1)[0]
    shown, _ = distinct_jobs(sample_id)
    names, lines = [], []
    for name, raw, _ in shown:
        header, hits = error_lines(clean(list(raw)))
        names += [name, header]
        lines += hits
    where, text = " ".join(names), "\n".join(lines)
    dependency = re.compile(DEPENDENCY.pattern.replace("{repo}", re.escape(repo)), re.I)
    if CI_CONFIG.search(text):
        category, confidence = "ci_config", "high"
    elif INFRA.search(text):
        category, confidence = "flaky_infra", "high"
    elif dependency.search(text):
        category, confidence = "dependency_env", "low"
    elif CHECK_JOB.search(where) or CHECK_TEXT.search(text):
        category, confidence = "static_check", "high"
    elif COMPILE.search(text):
        category, confidence = "code_defect", "low"
    elif TEST_ASSERT.search(text):
        category, confidence = "test_issue", "low"
    elif TEST_FAIL.search(text):
        category, confidence = "code_defect", "low"
    else:
        category, confidence = "unsure", "low"
    files = []
    for path in PATH.findall(text):
        path = re.sub(r"^.*?/(site-packages|work/[\w.-]+/[\w.-]+)/", "", path)
        if path not in files and not path.startswith(("/", "usr/", "home/")):
            files.append(path)
    return {"id": sample_id, "category": category, "confidence": confidence, "evidence": [], "files": files[:3],
            "explanation": "rules"}


def main() -> None:
    split = sys.argv[1]
    if split != "dev":
        sys.exit("baselines run on test only in step 6, after the final system is frozen")
    OUT.mkdir(parents=True, exist_ok=True)
    ids = scored_ids("dev")
    majority = Counter(labels()[i]["category"] for i in ids).most_common(1)[0][0]
    with open(OUT / f"r0_majority.{split}.jsonl", "w") as out:
        for i in ids:
            out.write(json.dumps({"id": i, "category": majority, "confidence": "low", "evidence": [], "files": [],
                                  "explanation": "majority"}) + "\n")
    with open(OUT / f"r1_rules.{split}.jsonl", "w") as out:
        for i in ids:
            out.write(json.dumps(rules(i)) + "\n")
    print(f"majority class on dev: {majority}")


if __name__ == "__main__":
    main()
