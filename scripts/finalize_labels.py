"""Apply the adjudication to Claude's first-pass labels and write the frozen labels (plan step 4).

    python scripts/finalize_labels.py
"""
import json

claude = {row["id"]: row for row in map(json.loads, open("annotation/labels.claude.jsonl"))}
decided = {row["id"]: row for row in map(json.loads, open("annotation/adjudication.jsonl"))}
order = [line.strip() for line in open("annotation/samples.txt") if line.strip()]

with open("annotation/labels.jsonl", "w") as out:
    for i in order:
        row = decided.get(i, claude[i])
        out.write(json.dumps({"id": i, "category": row["category"], "files": row["files"]}) + "\n")
print(f"wrote {len(order)} labels, {len(decided)} adjudicated")
