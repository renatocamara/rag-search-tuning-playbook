"""
Run one question against the index and show what the retriever returns.

    python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode vector
    python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode hybrid
    python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode semantic --current
    python scripts/demo/query.py "price of ND415A" --mode hybrid --no-normalize
    python scripts/demo/query.py "warranty on HydroFill" --mode semantic --profile prefer-current --answer
    python scripts/demo/query.py "..." --mode hybrid --show-request     # print the exact JSON sent

Flags
    --current            shortcut for --filter "status eq 'current'"
    --filter EXPR        any OData filter, e.g. "brand eq 'Contoso Flow' and doc_type ne 'community_post'"
    --profile NAME       scoring profile (prefer-current)
    --answer             also generate a grounded answer with the chat model
    --top N              passages to return (default 5)
"""

import argparse
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import retrieval  # noqa: E402


def print_rows(rows, width=100):
    if not rows:
        print("  (no results)")
        return
    for i, r in enumerate(rows, 1):
        flag = "" if r["status"] == "current" else f"  <-- {r['status'].upper()}"
        rr = f"  reranker={r['reranker_score']:.2f}" if r["reranker_score"] is not None else ""
        print(f"{i:2d}. score={r['score']:.4f}{rr}  {r['doc_id']}  [{r['doc_type']}, {r['effective_date']}]{flag}")
        if r["part_numbers"]:
            print(f"    parts: {', '.join(r['part_numbers'])}")
        snippet = r["caption"] or r["content"]
        snippet = " ".join(snippet.split())
        print(textwrap.indent(textwrap.shorten(snippet, width=width * 2, placeholder=" ..."), "    "))
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--mode", default="hybrid", choices=retrieval.MODES)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--filter")
    ap.add_argument("--current", action="store_true")
    ap.add_argument("--profile")
    ap.add_argument("--no-normalize", action="store_true", help="do not add normalized part numbers to the search text")
    ap.add_argument("--answer", action="store_true")
    ap.add_argument("--show-request", action="store_true")
    args = ap.parse_args()

    filter_expr = args.filter
    if args.current:
        filter_expr = "status eq 'current'" if not filter_expr else f"({filter_expr}) and status eq 'current'"

    body, rows = retrieval.run(args.question, args.mode, top=args.top, filter_expr=filter_expr,
                               scoring_profile=args.profile, normalize_parts=not args.no_normalize)
    print(f"\nmode={args.mode}  filter={filter_expr or '-'}  profile={args.profile or '-'}  index={common.SEARCH_INDEX}\n")
    if args.show_request:
        common.print_json(body)
        print()
    print_rows(rows)
    if args.answer:
        print("=" * 80)
        print(retrieval.answer(args.question, rows))
        print()


if __name__ == "__main__":
    main()
