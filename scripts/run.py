"""Run ladder configurations through gemini-3.8-flash with the Batch API (plan sections 6 and 11).

    python scripts/run.py r1 smoke     # 3 synchronous requests from different configs; checks parsing and scoring
    python scripts/run.py r1 quote     # free token count of every request and the cost estimate
    python scripts/run.py r1 submit    # inline batches, each under the request size limit
    python scripts/run.py r1 status
    python scripts/run.py r1 fetch     # writes runs/r1/<config>.jsonl and appends runs/cost.jsonl

Rounds are defined in ROUNDS and only ever use the dev split.
"""
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent))
from inputs import CATEGORIES, SCHEMA, config, labels, prompt, scored_ids  # noqa: E402
from score import metrics  # noqa: E402

MODEL = "gemini-3.8-flash"
PRICE = {"input": 0.375, "output": 1.875}  # US$ per million tokens, batch (third-party figures, 2026-10-18)
SYNC_FACTOR = 2  # synchronous calls cost twice the batch price
MAX_BATCH_BYTES = 4_000_000  # ~1M tokens: a 15 MB batch hit the enqueued-token quota (429) on 2026-10-18
BUDGET = 30.0
OUTPUT_GUESS = {"low": 250, "medium": 600}  # output tokens incl. thinking; r1 smoke measured ~180 and ~430
RUNS = Path("runs")

ROUNDS = {
    "r1": {f"r{rung}_tail{n}_{think}": (config(rung=rung, tail=n), think)
           for rung in (2, 3) for n in (100, 200, 400) for think in ("low", "medium")},
    # Round 2: rung 4 grid, the same grid with the PR file list (rung 5), and round 1's selected system plus the
    # file list, which is what the final system becomes if retrieval is not kept. Thinking fixed to low.
    "r2": {**{f"r{rung}_c{c}_k{k}_{q}": (config(rung=rung, chunk=c, k=k, query=q), "low")
              for rung in (4, 5) for c in (200, 400) for k in (4, 8) for q in ("fixed", "step")},
           "x_tail200_files": (config(rung=2, tail=200, files=1), "low")},
    # Round 3: rung 6 on the ladder (selected rung 5 + 3 / 6 examples), the same examples on the final system's
    # base (tail 200 + files, plan section 12 deviation), and prompt v2 on that base with 0 / 3 / 6 examples.
    "r3": {**{f"r6_c200_k4_fixed_s{n}": (config(rung=6, chunk=200, k=4, query="fixed", shots=n), "low")
              for n in (3, 6)},
           **{f"x_tail200_files_s{n}": (config(rung=2, tail=200, files=1, shots=n), "low") for n in (3, 6)},
           **{f"x_tail200_files_v2_s{n}": (config(rung=2, tail=200, files=1, shots=n, prompt=2), "low")
              for n in (0, 3, 6)}},
}


def requests(round_name: str) -> list[tuple[str, str, dict, str]]:
    """(key, sample id, config, thinking level) for every request of the round, dev split only."""
    out = []
    for name, (cfg, think) in ROUNDS[round_name].items():
        for sample_id in scored_ids("dev"):
            out.append((f"{name}|{sample_id}", sample_id, cfg, think))
    return out


def generation_config(system: str, think: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(system_instruction=system, temperature=0,
                                       response_mime_type="application/json", response_schema=SCHEMA,
                                       thinking_config=types.ThinkingConfig(thinking_level=think))


def parse(text: str | None) -> dict:
    """The answer if every field has the schema's type and values, else an error row (scored as unsure)."""
    try:
        row = json.loads(text or "")
        assert row["category"] in CATEGORIES + ["unsure"], "category"
        assert row["confidence"] in ("high", "low"), "confidence"
        for field in ("evidence", "files"):
            assert isinstance(row[field], list) and all(isinstance(x, str) for x in row[field]), field
        assert isinstance(row["explanation"], str), "explanation"
        return row
    except Exception as error:  # noqa: BLE001 - any malformed answer is scored as unsure
        return {"error": f"unparsable: {error!r}"[:200]}


def spent_so_far() -> float:
    path = RUNS / "cost.jsonl"
    return sum(json.loads(line)["usd"] for line in open(path)) if path.exists() else 0.0


def cost(usage, factor: float = 1) -> float:
    prompt_tokens = usage.prompt_token_count or 0
    output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    return factor * (prompt_tokens * PRICE["input"] + output_tokens * PRICE["output"]) / 1e6


def log_cost(entry: dict) -> None:
    with open(RUNS / "cost.jsonl", "a") as out:
        out.write(json.dumps(entry) + "\n")


def smoke(client, round_name: str) -> None:
    reqs = requests(round_name)
    picks = [reqs[0], reqs[len(reqs) // 2], reqs[-1]]
    total, rows = 0.0, []
    for key, sample_id, cfg, think in picks:
        system, user, _ = prompt(sample_id, cfg)
        response = client.models.generate_content(model=MODEL, contents=user,
                                                  config=generation_config(system, think))
        row = parse(response.text)
        spent = cost(response.usage_metadata, SYNC_FACTOR)
        total += spent
        print(key, "->", json.dumps(row, ensure_ascii=False)[:300])
        print("   usage:", response.usage_metadata.prompt_token_count, "in,",
              response.usage_metadata.candidates_token_count, "out,",
              response.usage_metadata.thoughts_token_count, "thinking", f"${spent:.4f}")
        assert "error" not in row, "smoke request did not parse"
        rows.append({"id": sample_id, **row})
    log_cost({"round": round_name, "what": "smoke", "requests": 3, "usd": round(total, 4), "at": time.time()})
    # The scorer must accept what the model returns.
    result = metrics([r["id"] for r in rows], labels(), {r["id"]: r for r in rows})
    print(f"scored {result['n']} smoke answers, accuracy {result['accuracy']:.2f}")
    print(f"smoke ok, spent ${total:.4f}")


def quote(client, round_name: str) -> None:
    reqs = requests(round_name)
    counted: dict[tuple, int] = {}
    total_in, total_out = 0, 0
    for key, sample_id, cfg, think in reqs:
        cache_key = (sample_id, json.dumps(cfg, sort_keys=True))
        if cache_key not in counted:
            system, user, _ = prompt(sample_id, cfg)
            counted[cache_key] = client.models.count_tokens(model=MODEL, contents=system + "\n\n" + user).total_tokens
        total_in += counted[cache_key]
        total_out += OUTPUT_GUESS[think]
    usd = (total_in * PRICE["input"] + total_out * PRICE["output"]) / 1e6
    print(f"{len(reqs)} requests, {total_in:,} input tokens, ~{total_out:,} output tokens (guess)")
    print(f"estimated batch cost ${usd:.2f}; spent so far ${spent_so_far():.2f}; budget cap ${BUDGET:.0f}")
    (RUNS / round_name).mkdir(parents=True, exist_ok=True)
    (RUNS / round_name / "quote.json").write_text(json.dumps({"requests": len(reqs), "inputTokens": total_in,
                                                              "outputTokensGuess": total_out, "usd": usd}))


def submit(client, round_name: str) -> None:
    """Creates the round's batches, saving each job as soon as it exists, so a rerun after a failure resumes
    instead of paying twice. Refuses when spent + this round's quote would pass the budget."""
    folder = RUNS / round_name
    quote_path = folder / "quote.json"
    if not quote_path.exists():
        sys.exit("run quote first")
    estimate = json.loads(quote_path.read_text())["usd"]
    record_path = folder / "batches.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else []
    if not record and spent_so_far() + estimate > BUDGET:
        sys.exit(f"spent ${spent_so_far():.2f} + quote ${estimate:.2f} exceeds the ${BUDGET:.0f} budget")
    batches, current, size = [], [], 0
    for key, sample_id, cfg, think in requests(round_name):
        system, user, _ = prompt(sample_id, cfg)
        request = types.InlinedRequest(model=MODEL, contents=user, config=generation_config(system, think),
                                       metadata={"key": key})
        length = len(system) + len(user) + 4000
        if current and size + length > MAX_BATCH_BYTES:
            batches.append(current)
            current, size = [], 0
        current.append((key, request))
        size += length
    batches.append(current)
    for n, batch in enumerate(batches):
        if n < len(record):
            assert record[n]["keys"] == [k for k, _ in batch], "batch split changed since the last submit"
            continue
        try:
            job = client.batches.create(model=MODEL, src=[r for _, r in batch],
                                        config={"display_name": f"ci-explainer-{round_name}-{n}"})
        except Exception as error:  # noqa: BLE001 - quota: resume later, nothing is lost
            sys.exit(f"stopped at batch {n} of {len(batches)}: {str(error)[:160]}; rerun submit later")
        record.append({"job": job.name, "keys": [k for k, _ in batch]})
        record_path.write_text(json.dumps(record, indent=1))
        print(job.name, len(batch), f"({n + 1} of {len(batches)})")


def status(client, round_name: str) -> list:
    record = json.loads((RUNS / round_name / "batches.json").read_text())
    jobs = [client.batches.get(name=r["job"]) for r in record]
    for job in jobs:
        print(job.name, job.state.name)
    return jobs


def fetch(client, round_name: str) -> None:
    """Writes one answer file per config. Responses are matched to requests by the key sent as metadata, and
    the full set is checked. Each job's cost is logged once, however often fetch runs."""
    folder = RUNS / round_name
    record = json.loads((folder / "batches.json").read_text())
    logged_path = folder / "costed_jobs.json"
    logged = set(json.loads(logged_path.read_text())) if logged_path.exists() else set()
    answers: dict[str, dict] = {}
    for entry in record:
        job = client.batches.get(name=entry["job"])
        if job.state.name != "JOB_STATE_SUCCEEDED":
            sys.exit(f"{job.name} is {job.state.name}")
        items = job.dest.inlined_responses
        keys = [(item.metadata or {}).get("key") for item in items]
        if not all(keys):
            assert len(items) == len(entry["keys"]), "responses carry no keys and their count differs"
            keys = entry["keys"]
        assert len(set(keys)) == len(keys) and set(keys) <= set(entry["keys"]), "unexpected or repeated keys"
        job_cost = 0.0
        for key, item in zip(keys, items):
            if item.error or not item.response:
                answers[key] = {"error": str(item.error)[:200]}
                continue
            answers[key] = parse(item.response.text)
            if item.response.usage_metadata:
                job_cost += cost(item.response.usage_metadata)
        for key in set(entry["keys"]) - set(keys):
            answers[key] = {"error": "no response returned"}
        if job.name not in logged:
            log_cost({"round": round_name, "what": "batch", "job": job.name, "requests": len(items),
                      "usd": round(job_cost, 4), "at": time.time()})
            logged.add(job.name)
            logged_path.write_text(json.dumps(sorted(logged)))
    rows: dict[str, list[dict]] = {}
    for key, _, _, _ in requests(round_name):
        name, sample_id = key.split("|")
        rows.setdefault(name, []).append({"id": sample_id, **answers.get(key, {"error": "not submitted"})})
    for name, items in rows.items():
        (folder / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in items))
        print(f"{name}: {len(items)} answers, {sum('error' in r for r in items)} errors")
    print(f"spent so far ${spent_so_far():.2f}")


def main() -> None:
    round_name, action = sys.argv[1], sys.argv[2]
    client = genai.Client()
    RUNS.mkdir(exist_ok=True)
    {"smoke": smoke, "quote": quote, "submit": submit, "status": status, "fetch": fetch}[action](client, round_name)


if __name__ == "__main__":
    main()
