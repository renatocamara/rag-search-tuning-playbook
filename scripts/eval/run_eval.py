"""
Run the evaluation set against the index and report retrieval quality.

Without a fixed set of questions with known answers, every tuning change is
an opinion. With one, it is a number. This script measures retrieval (did
the right document come back, and how high) and, optionally, answer quality
(did the model give the expected answer, judged by a second model call).

    python scripts/eval/run_eval.py --mode vector
    python scripts/eval/run_eval.py --mode hybrid
    python scripts/eval/run_eval.py --mode semantic --current --profile prefer-current
    python scripts/eval/run_eval.py --mode semantic --current --answer         # slower, calls the chat model twice per question
    python scripts/eval/run_eval.py --compare results/<a>.json results/<b>.json

Metrics (per question, then averaged overall and per category)
    hit@1, hit@3, hit@5   an expected doc_id appears in the top 1 / 3 / 5 passages
    mrr                   1 / rank of the first expected doc_id (0 if none in top 5)
    part@3                an expected part number appears in the part_numbers of the top 3 passages
    stale@1               the top passage is not 'current' (archived or community): lower is better
    answer_ok             (with --answer) the judge model marked the answer correct

Results are written to results/<timestamp>-<label>.json for later comparison.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demo"))
import common  # noqa: E402
import retrieval  # noqa: E402

JUDGE_SYSTEM = """You grade answers from a customer care assistant.
Given the question, the expected answer and the assistant's answer, reply with exactly one word:
CORRECT if the assistant's answer contains the same key facts (part numbers, values, yes/no) as the expected answer,
INCORRECT otherwise. Extra correct detail is fine. A wrong or missing part number is INCORRECT."""


def load_eval():
    with open(os.path.join(common.DATA_DIR, "eval", "eval_set.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def score(q, rows):
    ranks = [i + 1 for i, r in enumerate(rows) if r["doc_id"] in q["expected_doc_ids"]]
    first = ranks[0] if ranks else None
    top3_parts = {p for r in rows[:3] for p in r["part_numbers"]}
    part_ok = (not q["expected_part_numbers"]) or any(p in top3_parts for p in q["expected_part_numbers"])
    return {
        "hit@1": 1.0 if first == 1 else 0.0,
        "hit@3": 1.0 if first and first <= 3 else 0.0,
        "hit@5": 1.0 if first and first <= 5 else 0.0,
        "mrr": (1.0 / first) if first else 0.0,
        "part@3": 1.0 if part_ok else 0.0,
        "stale@1": 1.0 if rows and rows[0]["status"] != "current" else 0.0,
        "first_rank": first,
        "top1": rows[0]["doc_id"] if rows else None,
        "top1_status": rows[0]["status"] if rows else None,
    }


def judge(q, answer_text):
    verdict = common.chat(JUDGE_SYSTEM, f"Question: {q['question']}\nExpected: {q['expected_answer']}\nAssistant: {answer_text}")
    return 1.0 if verdict.strip().upper().startswith("CORRECT") else 0.0


def summarize(results):
    keys = ["hit@1", "hit@3", "hit@5", "mrr", "part@3", "stale@1"] + (["answer_ok"] if "answer_ok" in results[0] else [])
    overall = {k: sum(r[k] for r in results) / len(results) for k in keys}
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    cats = {c: {k: sum(r[k] for r in rs) / len(rs) for k in keys} for c, rs in sorted(by_cat.items())}
    return keys, overall, cats


def print_summary(label, keys, overall, cats, n):
    print(f"\n{label}  ({n} questions)")
    print("  " + "category".ljust(18) + "".join(k.rjust(10) for k in keys))
    print("  " + "ALL".ljust(18) + "".join(f"{overall[k]:10.2f}" for k in keys))
    for c, m in cats.items():
        print("  " + c.ljust(18) + "".join(f"{m[k]:10.2f}" for k in keys))


def compare(a_path, b_path):
    with open(a_path, encoding="utf-8") as f:
        a = json.load(f)
    with open(b_path, encoding="utf-8") as f:
        b = json.load(f)
    keys = [k for k in a["overall"] if k in b["overall"]]
    print(f"\n{'metric':12s}{a['label']:>28s}{b['label']:>28s}{'delta':>10s}")
    for k in keys:
        d = b["overall"][k] - a["overall"][k]
        print(f"{k:12s}{a['overall'][k]:28.2f}{b['overall'][k]:28.2f}{d:+10.2f}")
    print("\nper question (only where top-1 changed):")
    bq = {r["id"]: r for r in b["results"]}
    for r in a["results"]:
        o = bq.get(r["id"])
        if o and (r["top1"] != o["top1"] or r["hit@1"] != o["hit@1"]):
            print(f"  {r['id']} [{r['category']}] {r['question'][:55]:55s}\n"
                  f"      A: {r['top1']} ({r['top1_status']})  hit@1={r['hit@1']:.0f}\n"
                  f"      B: {o['top1']} ({o['top1_status']})  hit@1={o['hit@1']:.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="hybrid", choices=retrieval.MODES)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--filter")
    ap.add_argument("--current", action="store_true")
    ap.add_argument("--profile")
    ap.add_argument("--no-normalize", action="store_true")
    ap.add_argument("--answer", action="store_true", help="generate answers and judge them (slower)")
    ap.add_argument("--label", help="name for this run (default: built from the options)")
    ap.add_argument("--only", nargs="*", help="run only these question ids")
    ap.add_argument("--compare", nargs=2, metavar="JSON", help="compare two result files instead of running")
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
        return

    filter_expr = args.filter
    if args.current:
        filter_expr = "status eq 'current'" if not filter_expr else f"({filter_expr}) and status eq 'current'"
    label = args.label or "-".join(x for x in [
        args.mode, "current" if args.current else None, args.profile, "nonorm" if args.no_normalize else None,
        "answer" if args.answer else None] if x)

    questions = load_eval()
    if args.only:
        questions = [q for q in questions if q["id"] in args.only]
    results = []
    t0 = time.time()
    for q in questions:
        _, rows = retrieval.run(q["question"], args.mode, top=args.top, filter_expr=filter_expr,
                                scoring_profile=args.profile, normalize_parts=not args.no_normalize)
        s = score(q, rows)
        if args.answer:
            ans = retrieval.answer(q["question"], rows)
            s["answer"] = ans
            s["answer_ok"] = judge(q, ans)
        s.update(id=q["id"], category=q["category"], question=q["question"])
        results.append(s)
        mark = "ok " if s["hit@3"] else "MISS"
        stale = " stale-top1" if s["stale@1"] else ""
        print(f"  {mark} {q['id']} [{q['category']:15s}] rank={s['first_rank'] or '-'} top1={s['top1']}{stale}")

    keys, overall, cats = summarize(results)
    print_summary(label, keys, overall, cats, len(results))
    print(f"  elapsed {time.time() - t0:.0f}s")

    os.makedirs(common.RESULTS_DIR, exist_ok=True)
    out = os.path.join(common.RESULTS_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"label": label, "mode": args.mode, "filter": filter_expr, "profile": args.profile,
                   "index": common.SEARCH_INDEX, "overall": overall, "by_category": cats, "results": results},
                  f, indent=2)
    print(f"  saved {os.path.relpath(out, common.ROOT)}")


if __name__ == "__main__":
    main()
