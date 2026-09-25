"""
Build and run Azure AI Search queries in the four retrieval modes the
playbook compares. This is the file to read if you want to copy the exact
request body into your own application.

    keyword    BM25 full text search only            {"search": "..."}
    vector     nearest neighbours on the embedding   {"vectorQueries": [...]}   (no "search")
    hybrid     both, fused with Reciprocal Rank Fusion
    semantic   hybrid + semantic ranker (L2 reranking on the top 50)

Options that apply to every mode:
    filter_expr       OData filter, for example "status eq 'current'" or "is_canonical eq true"
    scoring_profile   name of a scoring profile defined in the index, for example "prefer-current"
    normalize_parts   append normalized part numbers found in the question (cf1100xls) so the
                      keyword leg can match the part_numbers_normalized field exactly
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402

SELECT = "chunk_id,doc_id,title,section,status,doc_type,brand,effective_date,source,source_tier,is_canonical,part_numbers,content"
MODES = ("keyword", "vector", "hybrid", "semantic")


def build_filter(filter_expr=None, current=False, canonical=False):
    """Compose the OData filter from the command line flags."""
    parts = []
    if filter_expr:
        parts.append(f"({filter_expr})")
    if current:
        parts.append("status eq 'current'")
    if canonical:
        parts.append("is_canonical eq true")
    return " and ".join(parts) if parts else None


def search_text(question, normalize_parts=True):
    if not normalize_parts:
        return question
    extra = list(common.extract_part_numbers(question, common.known_parts()).keys())
    return question if not extra else f"{question} {' '.join(extra)}"


def build_query(question, mode, top=5, filter_expr=None, scoring_profile=None, normalize_parts=True,
                vector=None, k=50):
    body = {"top": top, "select": SELECT}
    if mode in ("keyword", "hybrid", "semantic"):
        body["search"] = search_text(question, normalize_parts)
        body["queryType"] = "simple"
        body["searchMode"] = "any"
    if mode in ("vector", "hybrid", "semantic"):
        body["vectorQueries"] = [{
            "kind": "vector",
            "vector": vector,
            "fields": "content_vector",
            "k": k,
            "exhaustive": False,
        }]
    if mode == "semantic":
        body["queryType"] = "semantic"
        body["semanticConfiguration"] = common.SEMANTIC_CONFIG
        body["captions"] = "extractive"
    if filter_expr:
        body["filter"] = filter_expr
        body["vectorFilterMode"] = "preFilter"
    if scoring_profile and mode != "vector":
        body["scoringProfile"] = scoring_profile
        body["scoringParameters"] = ["preferStatus-current"]
    return body


def run(question, mode, **kw):
    """Return (request_body_without_vector, results list)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    vector = common.embed(question)[0] if mode != "keyword" else None
    body = build_query(question, mode, vector=vector, **kw)
    res = common.search_query(body)
    rows = []
    for r in res.get("value", []):
        rows.append({
            "score": r.get("@search.score"),
            "reranker_score": r.get("@search.rerankerScore"),
            "chunk_id": r["chunk_id"],
            "doc_id": r["doc_id"],
            "title": r.get("title"),
            "section": r.get("section"),
            "status": r.get("status"),
            "doc_type": r.get("doc_type"),
            "brand": r.get("brand"),
            "effective_date": (r.get("effective_date") or "")[:10],
            "source": r.get("source"),
            "source_tier": r.get("source_tier"),
            "is_canonical": r.get("is_canonical"),
            "part_numbers": r.get("part_numbers") or [],
            "content": r.get("content", ""),
            "caption": ((r.get("@search.captions") or [{}])[0].get("text") if mode == "semantic" else None),
        })
    shown = dict(body)
    if "vectorQueries" in shown:
        shown["vectorQueries"] = [dict(v, vector=f"<{len(v['vector'])} floats>") for v in shown["vectorQueries"]]
    return shown, rows


ANSWER_SYSTEM = """You are a Customer Care assistant for Contoso Water Solutions.
Answer the question using ONLY the passages provided. Quote part numbers exactly as written.
If the passages disagree, prefer the passage that is canonical, has status 'current' and the lower source tier
(1 is the official website), and say which document you used.
If the answer is not in the passages, say "I could not find that in the knowledge base."
Always end with: Sources: <doc_id list>."""


BARE_SYSTEM = """You are a Customer Care assistant for Contoso Water Solutions.
Answer the question using ONLY the passages provided. Quote part numbers exactly as written.
If the answer is not in the passages, say "I could not find that in the knowledge base."
Always end with: Sources: <passage numbers>."""


def answer(question, rows, with_metadata=True):
    """Grounded answer. with_metadata=False sends the same passages as plain text, the way many
    first-generation RAG applications do: the model then has no way to tell a canonical, current,
    tier 1 passage from a SharePoint copy or an archived page, and resolves contradictions on its own."""
    if with_metadata:
        passages = "\n\n".join(
            f"[{i + 1}] doc_id={r['doc_id']} status={r['status']} source={r.get('source')} tier={r.get('source_tier')} "
            f"canonical={r.get('is_canonical')} doc_type={r['doc_type']} effective={r['effective_date']}\n{r['content']}"
            for i, r in enumerate(rows))
        return common.chat(ANSWER_SYSTEM, f"Question: {question}\n\nPassages:\n{passages}")
    passages = "\n\n".join(f"[{i + 1}]\n{r['content']}" for i, r in enumerate(rows))
    return common.chat(BARE_SYSTEM, f"Question: {question}\n\nPassages:\n{passages}")
