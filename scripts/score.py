"""Metrics for one prediction file, or a paired comparison of two (plan sections 7 and 8).

Scoring rules, fixed before any model ran (plan section 12 logs them):
- Scored samples: the split minus `undeterminable` labels (dev 50, test 85). The sensitivity set also drops the
  test samples the model under test helped label (annotation/sensitivity_excluded.txt; 74 remain).
- A missing or unparsable prediction counts as `unsure` with low confidence.
- `unsure` is wrong: a false negative for the true class, never a false positive.
- Macro-F1 averages over the classes that have at least one gold sample in the set being scored (all six in
  the full dev and test sets; a bootstrap resample may lack one). The denominator depends on the gold labels
  only, so two systems compared on the same resample share it. A class's F1 is 0 when it has no true positive.
- High confidence = confidence "high" and category not `unsure`. Precision = accuracy on those; coverage = their
  share of all scored samples.
- File hit@k: over scored samples whose gold category is code_defect, test_issue, static_check or ci_config and
  whose gold file list is not empty. A hit is any of the first k predicted paths matching any gold path: equal
  after normalising, or the gold path ending in "/" + predicted path when that path has a directory part.
- Coarse macro-F1 (secondary): code_defect and test_issue merged, since the log alone often cannot tell whether
  the code or the test is wrong.
- 95% intervals: percentile bootstrap, 2000 resamples of samples, seed 20261017; paired for comparisons.

    python scripts/score.py runs/r1/<config>.jsonl [--split dev|test] [--sensitivity]
    python scripts/score.py compare <a.jsonl> <b.jsonl> [--split ...] [--sensitivity]
"""
import json
import random
import sys
from collections import Counter

CATEGORIES = ["code_defect", "test_issue", "dependency_env", "static_check", "ci_config", "flaky_infra"]
FILE_CLASSES = {"code_defect", "test_issue", "static_check", "ci_config"}
SEED = 20261017
RESAMPLES = 2000


def load_jsonl(path: str) -> dict[str, dict]:
    return {row["id"]: row for row in map(json.loads, open(path))}


def scored(split: str, sensitivity: bool) -> list[str]:
    labels = load_jsonl("annotation/labels.jsonl")
    manifest = load_jsonl("data/manifest.jsonl")
    order = [line.strip() for line in open("annotation/samples.txt") if line.strip()]
    ids = [i for i in order if manifest[i]["split"] == split and labels[i]["category"] != "undeterminable"]
    if sensitivity:
        excluded = {line.strip() for line in open("annotation/sensitivity_excluded.txt") if line.strip()}
        ids = [i for i in ids if i not in excluded]
    return ids


def prediction(preds: dict, sample_id: str) -> dict:
    row = preds.get(sample_id) or {}
    category = row.get("category") if row.get("category") in CATEGORIES + ["unsure"] else "unsure"
    files = row.get("files") if isinstance(row.get("files"), list) else []
    return {"category": category, "confidence": row.get("confidence", "low"),
            "files": [f for f in files if isinstance(f, str)]}


def macro_f1(pairs: list[tuple[str, str]], merge: bool = False) -> float:
    def fold(c: str) -> str:
        return "code_or_test" if merge and c in ("code_defect", "test_issue") else c
    pairs = [(fold(g), fold(p)) for g, p in pairs]
    classes = sorted({g for g, _ in pairs})
    scores = []
    for c in classes:
        tp = sum(g == c and p == c for g, p in pairs)
        fp = sum(g != c and p == c for g, p in pairs)
        fn = sum(g == c and p != c for g, p in pairs)
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(scores) / len(scores)


def norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").strip()


def file_hit(gold: list[str], predicted: list[str], k: int) -> bool:
    gold_paths = [norm(g) for g in gold]
    for p in map(norm, predicted[:k]):
        if any(p == g or ("/" in p and g.endswith("/" + p)) for g in gold_paths):
            return True
    return False


def metrics(ids: list[str], labels: dict, preds: dict) -> dict:
    rows = [(labels[i], prediction(preds, i)) for i in ids]
    pairs = [(g["category"], p["category"]) for g, p in rows]
    high = [(g, p) for g, p in rows if p["confidence"] == "high" and p["category"] != "unsure"]
    file_rows = [(g, p) for g, p in rows if g["category"] in FILE_CLASSES and g["files"]]
    per_class = {}
    for c in CATEGORIES:
        tp = sum(g == c and p == c for g, p in pairs)
        predicted = sum(p == c for _, p in pairs)
        actual = sum(g == c for g, _ in pairs)
        per_class[c] = {"n": actual, "precision": tp / predicted if predicted else None,
                        "recall": tp / actual if actual else None}
    return {
        "n": len(ids),
        "macroF1": macro_f1(pairs),
        "accuracy": sum(g == p for g, p in pairs) / len(pairs),
        "coarseMacroF1": macro_f1(pairs, merge=True),
        "unsure": sum(p == "unsure" for _, p in pairs),
        "missing": sum(i not in preds for i in ids),
        "highPrecision": sum(g["category"] == p["category"] for g, p in high) / len(high) if high else None,
        "highCoverage": len(high) / len(ids),
        "fileN": len(file_rows),
        "fileHit1": sum(file_hit(g["files"], p["files"], 1) for g, p in file_rows) / len(file_rows) if file_rows else None,
        "fileHit3": sum(file_hit(g["files"], p["files"], 3) for g, p in file_rows) / len(file_rows) if file_rows else None,
        "perClass": per_class,
        "confusion": Counter(f"{g}->{p}" for g, p in pairs if g != p).most_common(),
    }


def interval(values: list[float]) -> list[float]:
    values = sorted(values)
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)]


def bootstrap(ids: list[str], stat) -> list[float]:
    rng = random.Random(SEED)
    return interval([stat([rng.choice(ids) for _ in ids]) for _ in range(RESAMPLES)])


def report(path: str, split: str, sensitivity: bool) -> dict:
    labels, preds = load_jsonl("annotation/labels.jsonl"), load_jsonl(path)
    ids = scored(split, sensitivity)
    result = metrics(ids, labels, preds)

    def f1(sample: list[str]) -> float:
        return macro_f1([(labels[i]["category"], prediction(preds, i)["category"]) for i in sample])
    result["macroF1CI"] = bootstrap(ids, f1)
    manifest = load_jsonl("data/manifest.jsonl")
    result["perRepo"] = {}
    for repo in sorted({manifest[i]["repo"] for i in ids}):
        repo_ids = [i for i in ids if manifest[i]["repo"] == repo]
        result["perRepo"][repo] = {"n": len(repo_ids), "macroF1": round(f1(repo_ids), 3),
                                   "accuracy": round(metrics(repo_ids, labels, preds)["accuracy"], 3)}
    return result


def compare(a: str, b: str, split: str, sensitivity: bool) -> dict:
    """Paired bootstrap of macro-F1(b) - macro-F1(a) on the same resampled samples."""
    labels, pa, pb = load_jsonl("annotation/labels.jsonl"), load_jsonl(a), load_jsonl(b)
    ids = scored(split, sensitivity)

    def diff(sample: list[str]) -> float:
        def f1(preds):
            return macro_f1([(labels[i]["category"], prediction(preds, i)["category"]) for i in sample])
        return f1(pb) - f1(pa)
    return {"n": len(ids), "difference": round(diff(ids), 3), "CI": bootstrap(ids, diff)}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    split = "test" if "--split" in sys.argv and sys.argv[sys.argv.index("--split") + 1] == "test" else "dev"
    args = [a for a in args if a not in ("dev", "test")]
    sensitivity = "--sensitivity" in sys.argv
    if args[0] == "compare":
        print(json.dumps(compare(args[1], args[2], split, sensitivity), indent=1))
    else:
        print(json.dumps(report(args[0], split, sensitivity), indent=1, default=str))


if __name__ == "__main__":
    main()
