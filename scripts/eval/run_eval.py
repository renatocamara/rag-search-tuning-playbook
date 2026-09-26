"""
Run the evaluation set against the index and report retrieval quality.

Without a fixed set of questions with known answers, every tuning change is
an opinion. With one, it is a number. This script measures retrieval (did
the right document come back, and how high) and, optionally, answer quality
(did the model give the expected answer, judged by a second model call).

    python scripts/eval/run_eval.py --mode vector
    python scripts/eval/run_eval.py --mode hybrid
    python scripts/eval/run_eval.py --mode semantic --current --profile prefer-current
    python scripts/eval/run_eval.py --mode semantic --current --canonical
    python scripts/eval/run_eval.py --mode semantic --current --answer         # also generate answers, graded by strings
    python scripts/eval/run_eval.py --mode semantic --current --answer --judge # plus a second model as judge (slower)
    python scripts/eval/run_eval.py --compare results/<a>.json results/<b>.json

Metrics (per question, then averaged overall and per category)
    hit@1, hit@3, hit@5   an expected doc_id appears in the top 1 / 3 / 5 passages
    mrr                   1 / rank of the first expected doc_id (0 if none in top 5)
    part@3                an expected part number appears in the part_numbers of the top 3 passages
    stale@1               the top passage is not 'current' (archived or community): lower is better
    noncanon@1            the top passage is a non-canonical copy (for example the SharePoint duplicate): lower is better
    contam@5              any of the top 5 passages is archived, community or non-canonical, i.e. the model receives
                          a contradicting source even if the top passage is right: lower is better
    answer_ok             (with --answer) the generated answer contains every must_contain string and none of
                          the must_not_contain strings (deterministic, no model involved)
    judge_ok              (with --judge) a second model compared the answer with expected_answer

Results are written to results/<timestamp>-<label>.json for later comparison.
"""

import argparse
import json
import os
import re
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


DESCRIPTION = """\
run_eval.py: run every question of the evaluation set through the retriever and score the result.

The evaluation set (data/eval/eval_set.jsonl) has one line per question with the answer key:
which documents contain the answer, which part numbers a correct answer must mention, and
which strings the generated answer must and must not contain. For each question the script
sends the search request in the chosen mode, takes the top passages and checks them against
that key. The output is one table: a row per category, a column per metric, values 0 to 1.

Run it before and after every change to the index, the filters, the chunking or the prompt,
then compare the two results files. Without this, every improvement is an opinion.
"""

EPILOG = """\
Metrics (each is an average over the questions, 0 to 1)
  hit@1        top passage comes from a correct document                        higher is better
  hit@3        a correct document is within the top 3 passages                   higher is better
  hit@5        a correct document is within the top 5, i.e. reached the model    higher is better
  mrr          average of 1/position of the first correct document               higher is better
  part@3       expected part number present in the top 3 passages                higher is better
  stale@1      top passage is archived or community content                      lower is better
  noncanon@1   top passage is a non-canonical copy (e.g. SharePoint duplicate)    lower is better
  contam@5     any archived, community or non-canonical passage in the top 5     lower is better
  answer_ok    (--answer) answer has every must_contain, no must_not_contain      higher is better
  judge_ok     (--answer --judge) a second model judged the answer correct        higher is better

Reading the table
  The first four say whether and where the right document appeared. The next three say what
  came along that should not have. The last two grade the final answer. A change that raises
  hit@1 on part_lookup but lowers descriptive has a cost; the categories exist to show it.

Examples
  python scripts/eval/run_eval.py --mode vector
  python scripts/eval/run_eval.py --mode semantic --current --canonical
  python scripts/eval/run_eval.py --mode semantic --current --canonical --answer
  python scripts/eval/run_eval.py --only q36 q37 --mode semantic --current
  python scripts/eval/run_eval.py --compare results/<a>.json results/<b>.json
"""


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
        "noncanon@1": 1.0 if rows and rows[0].get("is_canonical") is False else 0.0,
        "contam@5": 1.0 if any(r["status"] != "current" or r.get("is_canonical") is False for r in rows[:5]) else 0.0,
        "first_rank": first,
        "top1": rows[0]["doc_id"] if rows else None,
        "top1_status": rows[0]["status"] if rows else None,
    }


def _present(needle, text):
    """Whole-token match, case-insensitive, so that 'K-CF-1100-RK' does not match 'K-CF-1100-RK2'."""
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def grade_strings(q, answer_text):
    """Deterministic grading: every must_contain present, no must_not_contain present."""
    ok = all(_present(x, answer_text) for x in q.get("must_contain", []))
    bad = any(_present(x, answer_text) for x in q.get("must_not_contain", []))
    return 1.0 if ok and not bad else 0.0


def judge(q, answer_text):
    verdict = common.chat(JUDGE_SYSTEM, f"Question: {q['question']}\nExpected: {q['expected_answer']}\nAssistant: {answer_text}")
    return 1.0 if verdict.strip().upper().startswith("CORRECT") else 0.0


def summarize(results):
    keys = ["hit@1", "hit@3", "hit@5", "mrr", "part@3", "stale@1", "noncanon@1", "contam@5"]
    keys += [k for k in ("answer_ok", "judge_ok") if k in results[0]]
    overall = {k: sum(r[k] for r in results) / len(results) for k in keys}
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    cats = {c: {k: sum(r[k] for r in rs) / len(rs) for k in keys} for c, rs in sorted(by_cat.items())}
    return keys, overall, cats


LEGEND = {
    "hit@1":      "top passage comes from a correct document                  (higher is better)",
    "hit@3":      "a correct document is within the top 3 passages             (higher is better)",
    "hit@5":      "a correct document is within the top 5, i.e. reached the model (higher is better)",
    "mrr":        "average of 1/position of the first correct document          (higher is better)",
    "part@3":     "expected part number present in the top 3 passages           (higher is better)",
    "stale@1":    "top passage is archived or community content                 (lower is better)",
    "noncanon@1": "top passage is a non-canonical copy, e.g. SharePoint duplicate (lower is better)",
    "contam@5":   "any archived, community or non-canonical passage in the top 5 (lower is better)",
    "answer_ok":  "generated answer has every must_contain and no must_not_contain string (higher is better)",
    "judge_ok":   "a second model judged the generated answer correct           (higher is better)",
}


def print_summary(label, keys, overall, cats, n):
    print(f"\n{label}  ({n} questions)")
    print("  " + "category".ljust(18) + "".join(k.rjust(11) for k in keys))
    print("  " + "ALL".ljust(18) + "".join(f"{overall[k]:11.2f}" for k in keys))
    for c, m in cats.items():
        print("  " + c.ljust(18) + "".join(f"{m[k]:11.2f}" for k in keys))
    print("\n  All values are averages over the questions, 0 to 1. For each question the retriever returns the top 5")
    print("  passages and the script checks them against the expected documents and part numbers.")
    for k in keys:
        print(f"    {k:11s} {LEGEND[k]}")


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
    ap = argparse.ArgumentParser(prog="run_eval.py", description=DESCRIPTION, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="hybrid", choices=retrieval.MODES,
                    help="retrieval mode for every question (default hybrid; recommended semantic)")
    ap.add_argument("--top", type=int, default=5, help="passages retrieved per question (default 5)")
    ap.add_argument("--filter", metavar="EXPR", help="OData filter applied to every question")
    ap.add_argument("--current", action="store_true", help="filter: status eq 'current'")
    ap.add_argument("--canonical", action="store_true", help="filter: is_canonical eq true (drops non-canonical copies)")
    ap.add_argument("--profile", metavar="NAME", help="scoring profile to apply, e.g. prefer-current")
    ap.add_argument("--no-normalize", action="store_true", help="do not append normalized part numbers to the search text")
    ap.add_argument("--answer", action="store_true", help="generate answers and grade them with must_contain strings")
    ap.add_argument("--judge", action="store_true", help="with --answer: also ask a second model to judge (slower)")
    ap.add_argument("--no-metadata", action="store_true", help="with --answer: passages sent as bare text, no labels")
    ap.add_argument("--label", help="name for this run, used in the results file name (default: built from the options)")
    ap.add_argument("--only", nargs="*", metavar="QID", help="run only these question ids, e.g. --only q36 q37")
    ap.add_argument("--compare", nargs=2, metavar="JSON", help="compare two results/*.json files instead of running")
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
        return

    filter_expr = retrieval.build_filter(args.filter, args.current, args.canonical)
    label = args.label or "-".join(x for x in [
        args.mode, "current" if args.current else None, "canonical" if args.canonical else None, args.profile,
        "nonorm" if args.no_normalize else None, "answer" if args.answer else None,
        "nometa" if args.no_metadata else None] if x)

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
            ans = retrieval.answer(q["question"], rows, with_metadata=not args.no_metadata)
            s["answer"] = ans
            s["answer_ok"] = grade_strings(q, ans)
            if args.judge:
                s["judge_ok"] = judge(q, ans)
        s.update(id=q["id"], category=q["category"], question=q["question"])
        results.append(s)
        mark = "ok " if s["hit@3"] else "MISS"
        stale = " stale-top1" if s["stale@1"] else (" noncanonical-top1" if s["noncanon@1"] else "")
        ans = "" if not args.answer else ("  answer=ok" if s["answer_ok"] else "  answer=WRONG")
        print(f"  {mark} {q['id']} [{q['category']:15s}] rank={s['first_rank'] or '-'} top1={s['top1']}{stale}{ans}")

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
