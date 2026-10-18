"""The report's three figures as standalone SVG (plan section 7), drawn from runs/test/RESULTS.json and the
dev scores, so they can be regenerated after any rescoring.

    python scripts/figures.py      # writes docs/figures/{ladder,precision_coverage,confusion}.svg
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score import CATEGORIES, load_jsonl, prediction, report, scored  # noqa: E402

OUT = Path("docs/figures")
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#a3a29b"
RAMP = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
FONT = "font-family=\"-apple-system, 'Helvetica Neue', sans-serif\""

LADDER = [  # label, test system name, dev prediction file, colour
    ("Rung 0\nmajority", "rung0 majority", "runs/baselines/r0_majority.dev.jsonl", GRAY),
    ("Rung 1\nrules", "rung1 rules", "runs/baselines/r1_rules.dev.jsonl", GRAY),
    ("Rung 2\nLLM, log tail", "rung2 tail200", "runs/r1/r2_tail200_low.jsonl", BLUE),
    ("Rung 3\n+ cleaning", "rung3 +clean", "runs/r1/r3_tail200_low.jsonl", BLUE),
    ("Rung 4\n+ retrieval", "rung4 +retrieval", "runs/r2/r4_c200_k4_fixed.jsonl", BLUE),
    ("Rung 5\n+ PR files", "rung5 +PR files", "runs/r2/r5_c200_k4_fixed.jsonl", BLUE),
    ("Rung 6\n+ examples", "rung6 +3 examples", "runs/r3/r6_c200_k4_fixed_s3.jsonl", BLUE),
    ("Final\ntail + PR files", "final tail200+files", "runs/r2/x_tail200_files.jsonl", ORANGE),
]


def text(x, y, s, size=12, fill=INK, anchor="middle", weight="normal") -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;")
    return (f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{s}</text>')


def svg(width, height, body) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}"><rect width="{width}" height="{height}" fill="{SURFACE}"/>{"".join(body)}</svg>\n')


def ladder(results: dict) -> str:
    systems = results["85 (all)"]["systems"]
    w, h, left, right, top, bottom = 860, 440, 60, 20, 60, 90
    plot_w, plot_h = w - left - right, h - top - bottom
    y = lambda v: top + plot_h * (1 - v)  # noqa: E731
    body = [text(left, 26, "Ablation ladder: test macro-F1 (85 failures, bars show 95% CIs)", 15, anchor="start",
                 weight="600"),
            text(left, 46, "Bars: test set.  Diamonds: dev set (50 failures, used to choose configurations)", 12, INK2, anchor="start")]
    for v in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
        body.append(f'<line x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                    f'stroke="{GRID if v else AXIS}" stroke-width="1"/>')
        body.append(text(left - 8, y(v) + 4, f"{v:.1f}", 11, MUTED, anchor="end"))
    slot = plot_w / len(LADDER)
    bar = slot * 0.46
    for n, (label, name, dev_path, colour) in enumerate(LADDER):
        r = systems[name]
        cx = left + slot * (n + 0.5)
        top_y, base = y(r["macroF1"]), y(0)
        body.append(f'<path d="M{cx - bar / 2:.1f},{base:.1f} V{top_y + 4:.1f} q0,-4 4,-4 H{cx + bar / 2 - 4:.1f} '
                    f'q4,0 4,4 V{base:.1f} Z" fill="{colour}"/>')
        lo, hi = r["macroF1CI"]
        body.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(lo):.1f}" y2="{y(hi):.1f}" stroke="{INK2}" '
                    f'stroke-width="1.5"/>')
        for v in (lo, hi):
            body.append(f'<line x1="{cx - 5:.1f}" x2="{cx + 5:.1f}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                        f'stroke="{INK2}" stroke-width="1.5"/>')
        body.append(text(cx - bar / 2 - 3, top_y + 14, f"{r['macroF1']:.2f}", 12, INK, anchor="end",
                         weight="600"))
        dev = report(dev_path, "dev", False)["macroF1"]
        dx, dy = cx + bar / 2 + 9, y(dev)
        body.append(f'<path d="M{dx:.1f},{dy - 6:.1f} l6,6 l-6,6 l-6,-6 Z" fill="{SURFACE}" stroke="{INK2}" '
                    f'stroke-width="1.5"/>')
        for i, part in enumerate(label.split("\n")):
            body.append(text(cx, h - bottom + 22 + 16 * i, part, 12 if i == 0 else 11, INK if i == 0 else INK2))
    return svg(w, h, body)


def precision_coverage(results: dict) -> str:
    systems = results["85 (all)"]["systems"]
    w, h, left, right, top, bottom = 760, 460, 64, 250, 60, 60
    plot_w, plot_h = w - left - right, h - top - bottom
    x = lambda v: left + plot_w * v  # noqa: E731
    y = lambda v: top + plot_h * (1 - (v - 0.4) / 0.6)  # noqa: E731  (y axis 0.4 to 1.0)
    body = [text(left, 26, "Precision vs coverage: trust only confident answers, or all of them", 15, anchor="start", weight="600"),
            text(left, 46, "Test set, 85 failures. Left point: confidence = high only. Right point: all answers (unsure counts as wrong)", 12, INK2,
                 anchor="start"),
            f'<rect x="{x(0.5):.1f}" y="{y(1.0):.1f}" width="{x(1.0) - x(0.5):.1f}" height="{y(0.8) - y(1.0):.1f}" '
            f'fill="#1baf7a" fill-opacity="0.10"/>',
            text(x(0.52), y(0.97), "criterion 2 met", 11, "#0f6e4b", anchor="start")]
    for v in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        body.append(f'<line x1="{left}" x2="{x(1)}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>')
        body.append(text(left - 8, y(v) + 4, f"{v:.1f}", 11, MUTED, anchor="end"))
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        body.append(text(x(v), y(0.4) + 18, f"{v:.0%}", 11, MUTED))
    body.append(f'<line x1="{left}" x2="{x(1)}" y1="{y(0.4):.1f}" y2="{y(0.4):.1f}" stroke="{AXIS}"/>')
    body.append(text(left + plot_w / 2, h - 14, "Coverage (share of all failures whose answer is trusted)", 12, INK2))
    body.append(f'<text transform="translate(18,{top + plot_h / 2:.1f}) rotate(-90)" {FONT} font-size="12" '
                f'fill="{INK2}" text-anchor="middle">Share of trusted answers with the right category</text>')
    series = [("Rules (rung 1)", "rung1 rules", GRAY), ("Rung 2: log tail", "rung2 tail200", BLUE),
              ("Final: tail + PR files", "final tail200+files", ORANGE)]
    for name, key, colour in series:
        r = systems[key]
        p1, p2 = (r["highCoverage"], r["highPrecision"]), (1.0, r["accuracy"])
        body.append(f'<line x1="{x(p1[0]):.1f}" y1="{y(p1[1]):.1f}" x2="{x(p2[0]):.1f}" y2="{y(p2[1]):.1f}" '
                    f'stroke="{colour}" stroke-width="2"/>')
        for px, py in (p1, p2):
            body.append(f'<circle cx="{x(px):.1f}" cy="{y(py):.1f}" r="5" fill="{colour}" stroke="{SURFACE}" '
                        f'stroke-width="2"/>')
        body.append(text(x(p1[0]) - 8, y(p1[1]) + 4, f"{p1[1]:.2f} @ {p1[0]:.0%}", 11, INK2, anchor="end"))
        body.append(text(x(1) + 10, y(p2[1]) + 4, f"{name} {p2[1]:.2f}", 11, INK, anchor="start"))
    return svg(w, h, body)


def confusion() -> str:
    labels, preds = load_jsonl("annotation/labels.jsonl"), load_jsonl("runs/test/final.jsonl")
    ids = scored("test", False)
    columns = CATEGORIES + ["unsure"]
    counts = {(g, p): 0 for g in CATEGORIES for p in columns}
    for i in ids:
        counts[(labels[i]["category"], prediction(preds, i)["category"])] += 1
    names = {"code_defect": "code defect", "test_issue": "test issue", "dependency_env": "dependency / env",
             "static_check": "static check", "ci_config": "CI config", "flaky_infra": "flaky / infra",
             "unsure": "unsure"}
    cell, left, top = 72, 150, 120
    w, h = left + cell * len(columns) + 130, top + cell * len(CATEGORIES) + 40
    peak = max(counts.values())
    body = [text(20, 26, "Final system: confusion matrix (test set, 85 failures)", 15, anchor="start", weight="600"),
            text(20, 46, "Rows: label. Columns: the model's answer. Right: failures in the class and recall", 12, INK2, anchor="start")]
    for j, p in enumerate(columns):
        parts = names[p].split(" / ")  # the long names go on two lines
        for k, part in enumerate(parts):
            body.append(text(left + cell * (j + 0.5), top - 12 - 15 * (len(parts) - 1 - k), part, 11, INK2))
    for i, g in enumerate(CATEGORIES):
        row_total = sum(counts[(g, p)] for p in columns)
        body.append(text(left - 10, top + cell * (i + 0.5) + 4, names[g], 12, INK, anchor="end"))
        for j, p in enumerate(columns):
            n = counts[(g, p)]
            step = 0 if n == 0 else min(len(RAMP) - 1, 1 + round((len(RAMP) - 2) * n / peak))
            fill = RAMP[step]
            body.append(f'<rect x="{left + cell * j + 1}" y="{top + cell * i + 1}" width="{cell - 2}" '
                        f'height="{cell - 2}" rx="4" fill="{fill}" stroke="{INK if g == p else "none"}" '
                        f'stroke-width="{1.5 if g == p else 0}"/>')
            if n:
                body.append(text(left + cell * (j + 0.5), top + cell * (i + 0.5) + 5, str(n), 13,
                                 "#ffffff" if step >= 4 else INK, weight="600" if g == p else "normal"))
        recall = counts[(g, g)] / row_total if row_total else 0
        body.append(text(left + cell * len(columns) + 10, top + cell * (i + 0.5) + 4,
                         f"{row_total} · recall {recall:.0%}", 11, INK2, anchor="start"))
    return svg(w, h, body)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = json.load(open("runs/test/RESULTS.json"))
    (OUT / "ladder.svg").write_text(ladder(results))
    (OUT / "precision_coverage.svg").write_text(precision_coverage(results))
    (OUT / "confusion.svg").write_text(confusion())
    print("wrote", ", ".join(str(p) for p in sorted(OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
