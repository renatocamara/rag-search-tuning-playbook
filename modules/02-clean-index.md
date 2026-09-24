# Module 02: A clean index (metadata, filters, scoring profiles)

**Symptom at Contoso:** "Which repair kit should I use on a CF-1100-XL?" is answered with `K-CF-1100-RK`, a kit discontinued in 2023. "What is the warranty on HydroFill bottle fillers?" gets "3 years" (the 2021 policy) instead of 5. The answers are not hallucinated; they are quoted faithfully from documents that should not have been consulted.

**Root cause:** the index was loaded with everything that could be crawled: the current site, the archived site, and the community forum. All of it has the same weight. The retriever has no way to know that the 2022 spec sheet for the CF-1100-XL is superseded by the 2024 one, or that a forum reply is not engineering guidance.

**Fix:** metadata on every chunk (`status`, `doc_type`, `effective_date`, `brand`), a filter that excludes what should never be used, and a scoring profile that prefers current, recent, official content when a filter would be too blunt.

Time: 10 minutes. Requires: module 01 (use `--mode semantic` throughout).

## Step 1: See the contamination

```bash
python scripts/demo/query.py "Which repair kit should I use on a CF-1100-XL manufactured in 2025?" --mode semantic
python scripts/demo/query.py "What is the warranty on HydroFill bottle filling stations?" --mode semantic
python scripts/demo/query.py "How often should the FX-2200-B filter be replaced?" --mode semantic --answer
```

In each case one or more of the top passages is marked `<-- ARCHIVED` or `<-- COMMUNITY`. On the filter question the community thread ("we do every 6 months") competes with the install guide ("every 3,000 gallons or 12 months"), and the generated answer may hedge or pick the wrong one.

Facets show how much of the index is not current:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, "scripts"); import common
r = common.search_query({"search": "*", "top": 0, "facets": ["status", "doc_type"]})
print(r["@search.facets"])
EOF
```

In this dataset roughly a quarter of the chunks are archived or community. In a real crawl of a current site plus an archive, it is often more than half, and duplicates (the same spec as a PDF and as a web page) add to it.

## Step 2: Filter what should never be used

```bash
python scripts/demo/query.py "Which repair kit should I use on a CF-1100-XL manufactured in 2025?" --mode semantic --current
python scripts/demo/query.py "What is the warranty on HydroFill bottle filling stations?" --mode semantic --current
```

`--current` adds `"filter": "status eq 'current'"` and `"vectorFilterMode": "preFilter"` to the request. Pre-filtering applies the filter before the vector search, so the k nearest neighbours are all current documents rather than a list from which current ones are removed afterwards (post-filtering can return fewer than k results, or none).

Filters are OData expressions and compose:

```
status eq 'current' and doc_type ne 'community_post'
status eq 'current' and brand eq 'Fabrikam Fixtures'
part_numbers/any(p: p eq 'CF-1100-XLS')
effective_date ge 2024-01-01T00:00:00Z
```

Try them with `--filter "<expression>"`.

## Step 3: When a filter is too blunt, use a scoring profile

A rep servicing a discontinued CF-1101-XL still needs its archived spec sheet. Excluding archived content entirely breaks that case. A scoring profile expresses a preference instead of a rule:

```bash
python scripts/demo/query.py "rough-in for the CF-1101-XL" --mode semantic
python scripts/demo/query.py "rough-in for the CF-1101-XL" --mode semantic --current                  # nothing useful: the sheet is archived
python scripts/demo/query.py "rough-in for the CF-1101-XL" --mode semantic --profile prefer-current   # archived sheet still found, current bulletin ranked above it
```

The `prefer-current` profile (defined in `scripts/setup/index.json`) does three things: weights matches in `part_numbers` five times more than matches in `content`, boosts documents whose `status` matches the `preferStatus` parameter passed at query time, and boosts documents with a recent `effective_date`.

Three things to know about scoring profiles:

* **They can make results worse.** A freshness boost says "prefer the newest document", and the newest document is not always the most relevant one. On this dataset an early version of `prefer-current` with a freshness boost of 2.0 pushed the cross reference guide (dated 2025) above the product spec sheets (dated 2023) on plain part lookups, and dropped `hit@1` from 0.91 to 0.83. A document that mentions many part numbers (a catalog page, a policy, a cross reference table) is the usual beneficiary of a badly tuned profile. Always measure a profile with the evaluation set before enabling it; this is the single most convincing reason to have one.
* The profile is applied to the BM25 leg of a hybrid query, and depending on the API version and the semantic configuration's `rankingOrder`, also after semantic reranking (`03_index.py --boosted-reranker` sets `rankingOrder: boostedRerankerScore` explicitly).
* Agentic retrieval (knowledge bases) ignores scoring profiles entirely, so for that path the filter and the index content are the only levers.

## Step 4: The recommended combination

```bash
python scripts/demo/query.py "..." --mode semantic --current
```

* Filter out `community` always (or never index it; see below).
* Filter out `archived` by default; drop the filter only when the question is explicitly about a discontinued product (module 04's catalog lookup tells you that, because the part's `status` is `discontinued`), and use the scoring profile in that case so current documents still rank first.
* Treat the scoring profile as a tool for the no-filter case, not as a default. Measure it.

## Step 5: Measure

```bash
python scripts/eval/run_eval.py --mode semantic
python scripts/eval/run_eval.py --mode semantic --current --profile prefer-current
python scripts/eval/run_eval.py --compare results/<semantic>.json results/<semantic-current-prefer-current>.json
```

`stale@1` should drop to zero with the filter alone. Compare the run with and without `--profile`: if the profile lowers `hit@1` on `part_lookup` or `spec_value`, it is boosting the wrong documents, and the per-question diff shows which. Nothing else should get worse; if `descriptive` drops, a filter is excluding a document you needed, which is the kind of thing you only discover with an evaluation set.

## Where the metadata comes from in real life

This dataset has clean front matter. Real sources rarely do, and deriving metadata is most of the work of this module:

| Source | How to derive `status` / `doc_type` / `effective_date` |
|---|---|
| Current website crawl | `status = current`; `doc_type` from the URL pattern or page template (`/specs/`, `/install/`, `/warranty/`); `effective_date` from the page's last-modified header or a date in the document |
| Archived website | `status = archived` for the whole source. If it must be indexed at all, index it into the same index with that status, never as an undifferentiated copy |
| SharePoint / document library | Library columns (document type, product line, revision date); if the library has none, the folder path |
| Salesforce Knowledge | Article type and `LastPublishedDate`; only articles in `Online` status |
| Community / forum | `status = community`; consider not indexing it at all for an assistant that gives technical answers, or index only threads marked as accepted answers by employees |
| Duplicates (PDF and HTML of the same spec) | Pick a canonical source per document type and skip the other, or keep both but set `doc_id` to the same value so one replaces the other at ingestion |

Whatever the source, the rule is the same: **no chunk enters the index without `status`, `doc_type` and `effective_date`.** Once they are there, cleaning up is a filter change, not a re-crawl.

## What to change in your application

| Setting | Before | After |
|---|---|---|
| Index fields | text and vector | plus `status`, `doc_type`, `brand`, `effective_date`, `part_numbers` |
| Ingestion | everything, same weight | every chunk tagged; community excluded or tagged; archive tagged |
| Request | no filter | `filter: status eq 'current'` by default, relaxed by the application when the question is about a discontinued part |
| Request | no scoring profile | `scoringProfile: prefer-current`, `scoringParameters: ["preferStatus-current"]` |
| Grounding prompt | passages only | passages with `doc_id`, `status`, `effective_date`; instruction to prefer current and cite |

## References

* [Filters in vector and hybrid queries](https://learn.microsoft.com/azure/search/vector-search-filters)
* [OData filter syntax](https://learn.microsoft.com/azure/search/search-query-odata-filter)
* [Scoring profiles](https://learn.microsoft.com/azure/search/index-add-scoring-profiles) and [scoring profiles with semantic ranking](https://learn.microsoft.com/azure/search/semantic-how-to-enable-scoring-profiles)
