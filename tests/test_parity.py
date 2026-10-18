"""The workflow's prompt must be the evaluated final system's prompt (runs/FINAL.json), byte for byte.

    python tests/test_parity.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "action"))

import explain  # noqa: E402
import inputs  # noqa: E402


def main() -> None:
    final = inputs.config(**json.loads((ROOT / "runs/FINAL.json").read_text())["final"])
    checked, mismatched = 0, []
    for split in ("dev", "test"):
        for sample_id in inputs.scored_ids(split):
            jobs = {name: list(lines) for name, lines in inputs.raw_jobs(sample_id)}
            files = json.loads((inputs.SAMPLES / sample_id / "pr_files.json").read_text())
            evaluated = inputs.prompt(sample_id, final)[:2]
            if explain.build_prompt(jobs, files) != evaluated:
                mismatched.append(sample_id)
            checked += 1
    print(f"{checked} samples checked, {len(mismatched)} prompts differ: {mismatched[:10]}")
    sys.exit(1 if mismatched else 0)


if __name__ == "__main__":
    main()
