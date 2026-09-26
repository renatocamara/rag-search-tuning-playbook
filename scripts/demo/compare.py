"""
compare.py: same question, four retrieval modes, side by side.
Run it with no arguments for the explanation.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import retrieval  # noqa: E402


DESCRIPTION = """\
compare.py: the SAME question sent four times to the SAME index, one request per retrieval
mode, printed side by side. Shows that the retrieval mode is a decision of the application
(the JSON it sends), not of the service.

  keyword   full text search (BM25): exact words and part numbers
  vector    embedding similarity: meaning, not exact identifiers
  hybrid    keyword + vector in one request, rankings fused by Azure AI Search
  semantic  hybrid + the semantic ranker re-ordering the top 50 by how well each passage answers

Each line under a mode is one passage: document, section, part numbers found in it, and a
flag when it is ARCHIVED, COMMUNITY or NOT CANONICAL. For scores and the generated answer
use query.py; for numbers over the whole question set use eval/run_eval.py.
"""

EXAMPLES = """\
Examples
  python scripts/demo/compare.py "What repair kit fits the CF-1100-XLS?"
  python scripts/demo/compare.py "What repair kit fits the CF-1100-XLS?" --current
  python scripts/demo/compare.py "What is the filter capacity of the FX-2200-B?" --current --canonical
  python scripts/demo/compare.py "My flush valve keeps running. What should I check?" --modes vector semantic --top 3
"""


def main():
    ap = argparse.ArgumentParser(prog="compare.py", description=DESCRIPTION, epilog=EXAMPLES,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="the question, in quotes")
    ap.add_argument("--modes", nargs="*", default=list(retrieval.MODES), choices=retrieval.MODES,
                    help="which modes to run (default: all four)")
    ap.add_argument("--top", type=int, default=3, help="passages per mode (default 3)")
    ap.add_argument("--filter", metavar="EXPR", help="OData filter (see query.py for the fields)")
    ap.add_argument("--current", action="store_true", help="only status = current (no archive, no community)")
    ap.add_argument("--canonical", action="store_true", help="only canonical copies (no SharePoint duplicates)")
    ap.add_argument("--profile", metavar="NAME", help="scoring profile to apply, e.g. prefer-current")
    ap.add_argument("--no-normalize", action="store_true", help="do not append normalized part numbers to the search text")
    if len(sys.argv) == 1:
        ap.print_help()
        return
    args = ap.parse_args()
    if not args.question:
        ap.error("a question is required, in quotes")

    filter_expr = retrieval.build_filter(args.filter, args.current, args.canonical)

    print(f"\nQ: {args.question}")
    print(f"filter={filter_expr or '-'}  profile={args.profile or '-'}")
    print(f"Top {args.top} passages per mode. Flags mark passages a rep should not be answered from.\n")
    for mode in args.modes:
        _, rows = retrieval.run(args.question, mode, top=args.top, filter_expr=filter_expr,
                                scoring_profile=args.profile, normalize_parts=not args.no_normalize)
        print(f"--- {mode.upper()} ---")
        for i, r in enumerate(rows, 1):
            flag = "" if r["status"] == "current" else f"   <-- {r['status'].upper()}"
            if r["status"] == "current" and r.get("is_canonical") is False:
                flag = f"   <-- NOT CANONICAL ({r.get('source')})"
            parts = f"  parts={','.join(r['part_numbers'])}" if r["part_numbers"] else ""
            print(f"  {i}. {r['doc_id']:38s} {r['section'][:28]:28s}{parts}{flag}")
        print()


if __name__ == "__main__":
    main()
