"""Agreement between Claude's first-pass labels and Codex's blind labels (plan step 3).

Reports Cohen's kappa and raw agreement on the category, a confusion table, agreement on the relevant files
where both annotators gave files, and every disagreement for adjudication.

    python scripts/agreement.py annotation/labels.claude.jsonl annotation/codex_labels.jsonl
"""
import collections
import json
import sys

CATEGORIES = ["code_defect", "test_issue", "dependency_env", "static_check", "ci_config", "flaky_infra",
              "undeterminable"]


def load(path: str) -> dict[str, dict]:
    return {row["id"]: row for row in map(json.loads, open(path))}


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    first = collections.Counter(a for a, _ in pairs)
    second = collections.Counter(b for _, b in pairs)
    expected = sum(first[c] * second[c] for c in CATEGORIES) / (n * n)
    return (observed - expected) / (1 - expected)


def main() -> None:
    claude, codex = load(sys.argv[1]), load(sys.argv[2])
    missing = sorted(set(claude) - set(codex))
    ids = sorted(set(claude) & set(codex))
    pairs = [(claude[i]["category"], codex[i]["category"]) for i in ids]
    agree = sum(a == b for a, b in pairs)
    print(json.dumps({"samples": len(ids), "missingFromCodex": missing,
                      "categoryAgreement": f"{agree}/{len(ids)}", "categoryKappa": round(kappa(pairs), 3)}))

    print("\nconfusion (rows Claude, columns Codex):")
    short = [c[:9] for c in CATEGORIES]
    print(" " * 15 + " ".join(f"{s:>9}" for s in short))
    table = collections.Counter(pairs)
    for a in CATEGORIES:
        print(f"{a:>15}" + " ".join(f"{table[(a, b)]:>9}" for b in CATEGORIES))

    both = [i for i in ids if claude[i]["files"] and codex[i]["files"]]
    same = sum(set(claude[i]["files"]) == set(codex[i]["files"]) for i in both)
    overlap = sum(bool(set(claude[i]["files"]) & set(codex[i]["files"])) for i in both)
    print(f"\nfiles, where both gave files: identical {same}/{len(both)}, overlapping {overlap}/{len(both)}")

    print("\ndisagreements:")
    for i in ids:
        a, b = claude[i], codex[i]
        if a["category"] != b["category"] or (a["files"] and b["files"] and set(a["files"]) != set(b["files"])):
            print(json.dumps({"id": i, "claude": a["category"], "codex": b["category"],
                              "claudeFiles": a["files"], "codexFiles": b["files"],
                              "claudeReason": a["reason"], "codexReason": b["reason"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
