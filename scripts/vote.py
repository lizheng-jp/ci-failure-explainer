"""Majority vote of the three blind annotators on the disputed samples (plan step 4).

Category: the one at least two of Claude, Codex and Gemini chose. Files: those listed by at least two of the
annotators who chose that category. Where all three categories differ, or no file is shared, the written
adjudication stands and the sample is flagged.

    python scripts/vote.py        # writes annotation/adjudication.jsonl from adjudication.manual.jsonl and the votes
"""
import collections
import json

NO_FILES = {"dependency_env", "flaky_infra", "undeterminable"}


def load(path: str) -> dict[str, dict]:
    return {row["id"]: row for row in map(json.loads, open(path))}


def main() -> None:
    voters = {"claude": load("annotation/labels.claude.jsonl"), "codex": load("annotation/codex_labels.jsonl"),
              "gemini": load("annotation/gemini_labels.jsonl")}
    adjudicated = [json.loads(line) for line in open("annotation/adjudication.manual.jsonl")]
    rows = []
    for old in adjudicated:
        i = old["id"]
        votes = {name: labels[i] for name, labels in voters.items()}
        category, count = collections.Counter(v["category"] for v in votes.values()).most_common(1)[0]
        row = {"id": i, "votes": {name: v["category"] for name, v in votes.items()}}
        if count < 2:
            row.update(category=old["category"], files=old["files"], decidedBy="adjudication (three-way split)")
        else:
            backers = [name for name, v in votes.items() if v["category"] == category]
            listed = collections.Counter(f for name in backers for f in set(votes[name]["files"]))
            files = sorted(f for f, n in listed.items() if n >= 2)
            if category not in NO_FILES and not files and listed:
                files, by = old["files"], "majority category; adjudicated files (no shared file)"
            else:
                by = "majority (" + ", ".join(backers) + ")"
            row.update(category=category, files=[] if category in NO_FILES else files, decidedBy=by)
        row["adjudicationNote"] = old["note"]
        row["changedFromAdjudication"] = (row["category"], sorted(row["files"])) != (old["category"],
                                                                                   sorted(old["files"]))
        rows.append(row)
    with open("annotation/adjudication.jsonl", "w") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        mark = "CHANGED" if row["changedFromAdjudication"] else "same"
        print(f"{mark:8} {row['id']:28} {row['category']:15} {row['decidedBy']}  {row['votes']}")


if __name__ == "__main__":
    main()
