"""
query.py: run one question against the index and show what the retriever returns,
optionally followed by the answer a Customer Care rep would see.

Run it with no arguments for the full explanation of every option.
"""

import argparse
import os
import re
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import retrieval  # noqa: E402

DESCRIPTION = """\
query.py: ask ONE question and see what the retriever returns.

What it does, step by step
  1. Turns your question into a search request for Azure AI Search (the same
     HTTP request an application such as a Function App /query endpoint sends).
  2. Prints the top passages (chunks of documents) the index returned. That is
     the raw material a RAG application hands to the language model.
  3. With --answer, also sends those passages to the chat model and prints the
     answer the way a rep would read it in the chat window.

Nothing is cached and nothing is written; run it as often as you like.
"""

EPILOG = """\
Options explained

  --mode  How the index is searched. Same index, same documents, different request:
    keyword   Full text search (BM25). Matches the words you typed against the text of
              each chunk. Exact tokens such as part numbers match well; meaning does not
              ("valve keeps running" does not match "continuous flow").
    vector    Semantic similarity. The question is turned into an embedding (a list of
              3072 numbers, via text-embedding-3-large) and the index returns the chunks
              whose embedding is closest. Meaning matches well; exact identifiers do not
              (CF-1100-XL and CF-1100-XLS are almost the same point in that space).
    hybrid    Both of the above in ONE request to Azure AI Search. The service runs the
              keyword search and the vector search in parallel and fuses the two rankings
              (Reciprocal Rank Fusion). The search happens inside the Azure AI Search
              service; the script only builds the request and embeds the question.
    semantic  Hybrid, plus the semantic ranker: after the fusion, a second model inside
              Azure AI Search reads the question and each of the top 50 candidates together
              and re-orders them by how well the passage answers the question (score 0 to 4).
              This is the recommended mode.

  --top N        How many passages to return and show (default 5). Azure AI Search accepts
                 up to 1000 for keyword/hybrid and 50 for semantic reranking, but a RAG
                 application typically passes 3 to 10 to the model; more is not better.

  --filter EXPR  Any OData filter on the filterable fields of the index:
                 status, doc_type, brand, source, source_tier, is_canonical, effective_date,
                 part_numbers, doc_id, chunking_strategy. Examples:
                   "brand eq 'Contoso Flow'"
                   "doc_type ne 'community_post'"
                   "effective_date ge 2024-01-01T00:00:00Z"
                   "part_numbers/any(p: p eq 'CF-1100-XLS')"
                 A filter is applied BEFORE the search, so excluded chunks never compete.

  --current      Shortcut for --filter "status eq 'current'". Removes archived documents and
                 community posts from the candidates. In practice: the agent can no longer
                 answer from the 2019 spec sheet or from a forum thread.

  --canonical    Shortcut for --filter "is_canonical eq true". Removes copies that are not
                 the authoritative version of a document, for example the spec sheet saved to
                 SharePoint at an older revision. In practice: when the same document exists
                 in two places, only the copy the ingestion marked as canonical is searched.

  --profile NAME Apply a scoring profile stored in the index (here: prefer-current), a rule
                 that boosts matches on part numbers, current status and recent dates without
                 excluding anything. Use it when a filter would be too blunt, for example a
                 question about a discontinued product whose only spec sheet is archived.
                 Measure it: a badly tuned profile makes results worse (module 02).

  --no-normalize By default the script detects part numbers in the question and appends a
                 normalized form (CF-1100-XLS -> cf1100xls) so the keyword search matches the
                 part_numbers_normalized field however the user typed it. This flag turns
                 that off, to show what happens when the application does not normalize.

  --answer       Also generate the final answer with the chat model (gpt-4.1-mini by default)
                 from the passages shown. This is what the rep would see.

  --no-metadata  With --answer: send the passages to the model as bare text, without doc_id,
                 status, source, tier, canonical flag or date. This is how many first
                 generation RAG applications work. Use it on a question whose passages
                 contradict each other and run it a few times: the answer changes.

  --show-request Print the exact JSON body sent to Azure AI Search. Useful to compare with
                 what your own application sends.

Reading the output
  Each numbered line is one passage (chunk). It shows the document it came from, the
  document type, the source, the effective date, the part numbers found in the chunk, and a
  flag when the chunk is ARCHIVED, COMMUNITY or NOT CANONICAL.
    score     relevance from the search itself (BM25, cosine similarity, or the fused RRF
              value for hybrid; only the order matters)
    reranker  semantic ranker score, 0 to 4, present only in --mode semantic
  The ANSWER block is what the rep would see. "Sources:" is the model naming the documents
  (doc_id) or passage numbers it relied on; the script then resolves every passage to its
  document title, source and date and marks the ones the answer cited.

Examples
  python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode vector
  python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode semantic --current --answer
  python scripts/demo/query.py "What is the list price of the FX-2200-B?" --mode semantic --current --canonical --answer
  python scripts/demo/query.py "price of ND415A" --mode hybrid --no-normalize
  python scripts/demo/query.py "What is the rough-in for the CF-1100-XLS?" --mode semantic --show-request
"""

MODE_NOTE = {
    "keyword": "score = BM25 text relevance (higher is a stronger word match).",
    "vector": "score = cosine similarity between the question embedding and the passage embedding.",
    "hybrid": "score = keyword and vector rankings fused with Reciprocal Rank Fusion; only the order matters.",
    "semantic": ("score = fused keyword+vector relevance (only the order matters); "
                 "reranker = semantic ranker, 0 to 4, a model that reads question and passage together "
                 "and orders the top 50 candidates."),
}


def print_rows(rows, width=100):
    if not rows:
        print("  (no results)")
        return
    for i, r in enumerate(rows, 1):
        flag = "" if r["status"] == "current" else f"  <-- {r['status'].upper()}"
        if r["status"] == "current" and r.get("is_canonical") is False:
            flag = f"  <-- NOT CANONICAL ({r.get('source')})"
        rr = f"  reranker={r['reranker_score']:.2f}" if r["reranker_score"] is not None else ""
        print(f"{i:2d}. score={r['score']:.4f}{rr}  {r['doc_id']}  [{r['doc_type']}, {r.get('source')}, {r['effective_date']}]{flag}")
        if r["part_numbers"]:
            print(f"    parts: {', '.join(r['part_numbers'])}")
        snippet = r["caption"] or r["content"]
        snippet = " ".join(snippet.split())
        print(textwrap.indent(textwrap.shorten(snippet, width=width * 2, placeholder=" ..."), "    "))
        print()


def print_sources(answer_text, rows, bare):
    """Resolve what the model cited to the documents behind the passages."""
    cited_nums = {int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", answer_text)}
    cited_docs = {r["doc_id"] for r in rows if r["doc_id"] in answer_text}
    print("\nWhere the answer came from (passage -> document):")
    for i, r in enumerate(rows, 1):
        cited = (i in cited_nums) or (r["doc_id"] in cited_docs)
        mark = "cited " if cited else "      "
        line = (f"  {mark}[{i}] {r['doc_id']}  |  {r.get('title') or ''}  |  "
                f"{r.get('source')}, tier {r.get('source_tier')}, {r['status']}, {r['effective_date']}")
        if r.get("is_canonical") is False:
            line += "  (not canonical)"
        print(line)
    if bare:
        print("  (bare mode: the model only saw passage numbers, not document names)")


def main():
    ap = argparse.ArgumentParser(prog="query.py", description=DESCRIPTION, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help='the question, in quotes, e.g. "What repair kit fits the CF-1100-XLS?"')
    ap.add_argument("--mode", default="hybrid", choices=retrieval.MODES,
                    help="keyword | vector | hybrid | semantic (default: hybrid; recommended: semantic)")
    ap.add_argument("--top", type=int, default=5, help="passages to return (default 5)")
    ap.add_argument("--filter", metavar="EXPR", help="OData filter on filterable fields (see below)")
    ap.add_argument("--current", action="store_true", help="only status = current (no archive, no community)")
    ap.add_argument("--canonical", action="store_true", help="only canonical copies (no SharePoint duplicates)")
    ap.add_argument("--profile", metavar="NAME", help="scoring profile to apply, e.g. prefer-current")
    ap.add_argument("--no-normalize", action="store_true", help="do not append normalized part numbers to the search text")
    ap.add_argument("--answer", action="store_true", help="also generate the answer the rep would see")
    ap.add_argument("--no-metadata", action="store_true", help="with --answer: passages sent as bare text, no labels")
    ap.add_argument("--show-request", action="store_true", help="print the exact JSON sent to Azure AI Search")
    if len(sys.argv) == 1:
        ap.print_help()
        return
    args = ap.parse_args()
    if not args.question:
        ap.error("a question is required, in quotes")

    filter_expr = retrieval.build_filter(args.filter, args.current, args.canonical)

    body, rows = retrieval.run(args.question, args.mode, top=args.top, filter_expr=filter_expr,
                               scoring_profile=args.profile, normalize_parts=not args.no_normalize)

    print(f"\nQuestion: {args.question}")
    print(f"mode={args.mode}  filter={filter_expr or '-'}  profile={args.profile or '-'}  index={common.SEARCH_INDEX}")
    if args.show_request:
        print("\nRequest body sent to Azure AI Search (vector shortened):")
        common.print_json(body)

    print(f"\n--- RETRIEVAL: top {args.top} passages the index returned (what a RAG application hands to the model) ---")
    print(MODE_NOTE[args.mode] + "\n")
    print_rows(rows)

    if args.answer:
        how = ("as bare text, no labels" if args.no_metadata
               else "labelled with doc_id, status, source, tier, canonical flag and date")
        print(f"--- ANSWER: what the rep would see. Generated by {common.CHAT_DEPLOYMENT} "
              f"from the {len(rows)} passages above, {how} ---\n")
        text = retrieval.answer(args.question, rows, with_metadata=not args.no_metadata)
        print(text)
        print_sources(text, rows, args.no_metadata)
        print()


if __name__ == "__main__":
    main()
