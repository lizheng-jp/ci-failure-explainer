"""Step 6: test-split results for every rung and the plan section 8 criteria (written before the test run).

Criteria, for a system S against the rules baseline (rung 1):
  1. macro-F1(S) - macro-F1(rules) >= 0.10 and the paired bootstrap 95% CI's lower bound > 0
  2. accuracy on high-confidence answers >= 0.80, on >= 50% of the scored samples
  3. file hit@1 >= 0.50
Checked for the final system (plan section 12 deviation) and for the final system under the original rules
(rung 2), on all 85 scored test samples and on the 74 the model under test did not help label.

    python scripts/criteria.py      # writes runs/test/RESULTS.json and prints the tables
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score import compare, report  # noqa: E402

SYSTEMS = {
    "rung0 majority": "runs/baselines/r0_majority.test.jsonl",
    "rung1 rules": "runs/baselines/r1_rules.test.jsonl",
    "rung2 tail200": "runs/test/rung2.jsonl",
    "rung3 +clean": "runs/test/rung3.jsonl",
    "rung4 +retrieval": "runs/test/rung4.jsonl",
    "rung5 +PR files": "runs/test/rung5.jsonl",
    "rung6 +3 examples": "runs/test/rung6.jsonl",
    "final tail200+files": "runs/test/final.jsonl",
}
CHECKED = {"final (deviation)": "final tail200+files", "final (original rules) = rung2": "rung2 tail200"}


def verdict(system: dict, versus_rules: dict) -> dict:
    return {
        "1 beats rules by >=0.10, CI>0": versus_rules["difference"] >= 0.10 and versus_rules["CI"][0] > 0,
        "2 high-conf precision >=0.80 on >=50%": (system["highPrecision"] or 0) >= 0.80
                                                 and system["highCoverage"] >= 0.50,
        "3 file hit@1 >=0.50": (system["fileHit1"] or 0) >= 0.50,
    }


def main() -> None:
    results = {}
    for sensitivity in (False, True):
        tag = "74 (sensitivity)" if sensitivity else "85 (all)"
        rows = {name: report(path, "test", sensitivity) for name, path in SYSTEMS.items()}
        names = list(SYSTEMS)
        ladder = {f"{a} -> {b}": compare(SYSTEMS[a], SYSTEMS[b], "test", sensitivity)
                  for a, b in zip(names[1:7], names[2:7])}
        checks = {}
        for label, name in CHECKED.items():
            versus = compare(SYSTEMS["rung1 rules"], SYSTEMS[name], "test", sensitivity)
            checks[label] = {"versusRules": versus, "criteria": verdict(rows[name], versus)}
        results[tag] = {"systems": rows, "ladder": ladder, "checks": checks}

        print(f"\n===== test, {tag} scored samples")
        print(f"{'system':22} {'macro-F1':>8} {'95% CI':>13} {'acc':>5} {'coarse':>6} {'unsure':>6} "
              f"{'highP':>5} {'cover':>5} {'file@1':>6} {'@3':>5}")
        for name, r in rows.items():
            def f(x):
                return "  -  " if x is None else f"{x:.2f}"
            print(f"{name:22} {r['macroF1']:8.3f} {str(r['macroF1CI']):>13} {r['accuracy']:5.2f} "
                  f"{r['coarseMacroF1']:6.2f} {r['unsure']:6} {f(r['highPrecision']):>5} {r['highCoverage']:5.2f} "
                  f"{f(r['fileHit1']):>6} {f(r['fileHit3']):>5}")
        print("ladder steps (paired macro-F1 difference, 95% CI):")
        for step, d in ladder.items():
            print(f"  {step:42} {d['difference']:+.3f} {d['CI']}")
        for label, c in checks.items():
            v = c["versusRules"]
            print(f"{label}: vs rules {v['difference']:+.3f} {v['CI']}")
            for criterion, passed in c["criteria"].items():
                print(f"    {'PASS' if passed else 'fail'}  {criterion}")
    Path("runs/test").mkdir(parents=True, exist_ok=True)
    Path("runs/test/RESULTS.json").write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
