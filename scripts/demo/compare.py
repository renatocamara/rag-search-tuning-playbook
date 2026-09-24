"""
Same question, four retrieval modes, side by side. The fastest way to show a
room what changes when you move from vector only to hybrid to semantic.

    python scripts/demo/compare.py "What repair kit fits the CF-1100-XLS?"
    python scripts/demo/compare.py "What repair kit fits the CF-1100-XLS?" --current
    python scripts/demo/compare.py "warranty on HydroFill bottle fillers" --profile prefer-current
    python scripts/demo/compare.py "..." --modes vector hybrid --top 3
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import retrieval  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--modes", nargs="*", default=list(retrieval.MODES), choices=retrieval.MODES)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--filter")
    ap.add_argument("--current", action="store_true")
    ap.add_argument("--profile")
    ap.add_argument("--no-normalize", action="store_true")
    args = ap.parse_args()

    filter_expr = args.filter
    if args.current:
        filter_expr = "status eq 'current'" if not filter_expr else f"({filter_expr}) and status eq 'current'"

    print(f"\nQ: {args.question}")
    print(f"filter={filter_expr or '-'}  profile={args.profile or '-'}\n")
    for mode in args.modes:
        _, rows = retrieval.run(args.question, mode, top=args.top, filter_expr=filter_expr,
                                scoring_profile=args.profile, normalize_parts=not args.no_normalize)
        print(f"--- {mode.upper()} ---")
        for i, r in enumerate(rows, 1):
            flag = "" if r["status"] == "current" else f"   <-- {r['status'].upper()}"
            parts = f"  parts={','.join(r['part_numbers'])}" if r["part_numbers"] else ""
            print(f"  {i}. {r['doc_id']:38s} {r['section'][:28]:28s}{parts}{flag}")
        print()


if __name__ == "__main__":
    main()
