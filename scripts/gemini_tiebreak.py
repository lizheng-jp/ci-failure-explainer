"""Third, blind annotator for the samples Claude and Codex disagreed on (plan step 4).

Gemini labels each disputed sample from the same rules and materials the
other annotators had, without seeing their labels. The final label is the majority of the three; where all
three differ, the adjudication stands.

    python scripts/gemini_tiebreak.py count            # free token count for every request
    python scripts/gemini_tiebreak.py smoke <id>       # one synchronous request, to check the output format
    python scripts/gemini_tiebreak.py run              # synchronous requests for the remaining ids
    python scripts/gemini_tiebreak.py submit           # batch for the remaining ids
    python scripts/gemini_tiebreak.py fetch <job>      # write annotation/gemini_labels.jsonl
"""
import json
import pathlib
import re
import sys

from google import genai
from google.genai import types

# A Pro batch (gemini-3.1-pro-preview) was submitted first but had not returned after 45 minutes; it was
# cancelled and the user chose the Flash model under test instead. See plan section 12.
MODEL = "gemini-3.8-flash"
CATEGORIES = ["code_defect", "test_issue", "dependency_env", "static_check", "ci_config", "flaky_infra",
              "undeterminable"]
SAMPLES = pathlib.Path("data/samples")
OUT = pathlib.Path("annotation/gemini_labels.jsonl")
ERROR = re.compile(r"error|fail|panic|exception|timed out|assert", re.I)
PASSED = re.compile(r"\bPASS\b|\.\.\. ok\b|\bok\s+\S+\s+[\d.]+s|PASSED")
STAMP = re.compile(r"^.*?\d{4}-\d\d-\d\dT[\d:.]+Z ")

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "files": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["category", "files", "reason"],
}


def disputed() -> list[str]:
    return [json.loads(line)["id"] for line in open("annotation/adjudication.manual.jsonl")]


def log_excerpt(path: pathlib.Path, limit: int = 150) -> str:
    """Error-looking lines of the complete log, which the condensed view can miss."""
    lines = []
    for raw in path.read_text(errors="replace").splitlines():
        line = STAMP.sub("", raw).strip()
        if ERROR.search(line) and not PASSED.search(line) and line not in lines:
            lines.append(line[:300])
    return "\n".join(lines[:limit])


def prompt(sample_id: str) -> str:
    folder = SAMPLES / sample_id
    rules = pathlib.Path("annotation/INSTRUCTIONS.md").read_text()
    rules = rules.split("## Output")[0]
    fix_files = (folder / "fix_files.json").read_text() if (folder / "fix_files.json").exists() else "[]"
    parts = [
        "You are an annotator. Follow these labelling rules exactly.\n\n" + rules,
        "Answer with JSON: category, files (paths exactly as in fix_files.json), reason (one short sentence).",
        f"## Sample {sample_id}\n\n### view.txt\n{(folder / 'view.txt').read_text()[:40000]}",
        f"### error-looking lines from failed.log (full log, de-duplicated)\n{log_excerpt(folder / 'failed.log')}",
        f"### fix_files.json\n{fix_files}",
    ]
    fix_pr = folder / "fix_pr.diff"
    if fix_pr.exists() and fix_pr.read_text().strip():
        parts.append(f"### fix_pr.diff\n{fix_pr.read_text()[:60000]}")
    elif (folder / "fix.diff").exists():
        parts.append(f"### fix.diff (fix_pr.diff is empty)\n{(folder / 'fix.diff').read_text()[:30000]}")
    return "\n\n".join(parts)


def config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                       response_schema=SCHEMA)


def save(sample_id: str, text: str) -> None:
    row = json.loads(text)
    row = {"id": sample_id, "category": row["category"], "files": row["files"], "reason": row["reason"]}
    with OUT.open("a") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))


def main() -> None:
    client = genai.Client()
    action = sys.argv[1]
    done = {json.loads(line)["id"] for line in OUT.open()} if OUT.exists() else set()
    if action == "count":
        total = 0
        for sample_id in disputed():
            n = client.models.count_tokens(model=MODEL, contents=prompt(sample_id)).total_tokens
            total += n
            print(sample_id, n)
        print("total input tokens", total)
    elif action == "smoke":
        sample_id = sys.argv[2]
        response = client.models.generate_content(model=MODEL, contents=prompt(sample_id), config=config())
        print(response.usage_metadata)
        save(sample_id, response.text)
    elif action == "run":
        for sample_id in [i for i in disputed() if i not in done]:
            response = client.models.generate_content(model=MODEL, contents=prompt(sample_id), config=config())
            save(sample_id, response.text)
    elif action == "submit":
        ids = [i for i in disputed() if i not in done]
        requests = [types.InlinedRequest(model=MODEL, contents=prompt(i), config=config(),
                                         metadata={"id": i}) for i in ids]
        job = client.batches.create(model=MODEL, src=requests, config={"display_name": "label-tiebreak"})
        print(job.name, len(ids))
    elif action == "fetch":
        job = client.batches.get(name=sys.argv[2])
        print(job.state)
        if job.state.name != "JOB_STATE_SUCCEEDED":
            return
        for item in job.dest.inlined_responses:
            sample_id = item.metadata["id"]
            if item.error or sample_id in done:
                print(sample_id, item.error)
                continue
            save(sample_id, item.response.text)


if __name__ == "__main__":
    main()
