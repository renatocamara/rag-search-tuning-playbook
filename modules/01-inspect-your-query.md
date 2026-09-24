# Module 01: Inspect your query (vector, keyword, hybrid, semantic)

**Symptom at Contoso:** "What repair kit fits the CF-1100-XLS?" comes back with the CF-1100-XL or the CF-1101-XL spec sheet. Reps stop trusting the assistant on the one thing they ask most: part numbers.

**Root cause:** the application sends only a vector to Azure AI Search. Embeddings capture meaning, and to an embedding model `CF-1100-XL`, `CF-1100-XLS` and `CF-1101-XL` mean almost the same thing. Nothing in the request asks for an exact match on the string.

**Fix:** send the text too (hybrid), turn on the semantic ranker, and make sure the part number field has an analyzer that matches whole strings.

Time: 10 minutes. Requires: setup steps 1 to 4 done with the default (`structured`) chunking.

## Step 1: Look at what is actually sent

Before changing anything, print the request body. This is the question to ask of any RAG system that "uses AI Search": what does the JSON look like?

```bash
python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode vector --show-request
```

```json
{
  "top": 5,
  "select": "chunk_id,doc_id,...",
  "vectorQueries": [ { "kind": "vector", "vector": "<3072 floats>", "fields": "content_vector", "k": 50 } ]
}
```

No `search` field. The service never sees the words "CF-1100-XLS"; it sees a point in a 3,072-dimensional space that is very close to the points for the CF-1100-XL and the CF-1101-XL sheets.

Typical result (the exact order varies with the embedding model):

```
 1. score=0.87  spec-CF-1100-XL      [spec_sheet, 2024-07-01]
 2. score=0.86  spec-CF-1100-XLS     [spec_sheet, 2024-07-01]
 3. score=0.86  spec-CF-1101-XL-2019 [spec_sheet, 2019-03-01]   <-- ARCHIVED
 4. score=0.85  faq-contoso-flow
 5. score=0.85  spec-CF-1100-XL-2022 [spec_sheet, 2022-01-10]   <-- ARCHIVED
```

The right document is there, but not first, and its neighbours contradict it (the archived sheets say the kit is `K-CF-1100-RK`). Whether the model answers correctly is now luck.

## Step 2: Add the text (hybrid)

```bash
python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode hybrid --show-request
```

```json
{
  "search": "What repair kit fits the CF-1100-XLS? cf1100xls",
  "queryType": "simple",
  "vectorQueries": [ { "kind": "vector", "vector": "<3072 floats>", "fields": "content_vector", "k": 50 } ],
  ...
}
```

Two things changed. There is a `search` string, so BM25 full-text scoring runs alongside the vector query and the two rankings are fused (Reciprocal Rank Fusion). And the script appended `cf1100xls`, the normalized form of the part number it detected in the question, which hits the `part_numbers_normalized` field exactly.

The CF-1100-XLS spec sheet now ranks first, because it is the only document whose `part_numbers` field contains that exact token, and that field has a weight of 5 in the default ranking.

## Step 3: Add the semantic ranker

```bash
python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode semantic
```

```json
{
  "search": "...",
  "queryType": "semantic",
  "semanticConfiguration": "contoso-semantic",
  "captions": "extractive",
  "vectorQueries": [ ... ]
}
```

The semantic ranker reranks the top 50 fused results with a cross-encoder that reads the query and each passage together. The result shows a `reranker` score (0 to 4) next to the BM25/RRF score and a caption, the sentence the ranker considered most relevant. For part number questions the reranker helps most when the keyword leg surfaced the right document but ranked it third or fourth; for descriptive questions ("my valve keeps running") it is the biggest single improvement.

## Step 4: See all four side by side

```bash
python scripts/demo/compare.py "What repair kit fits the CF-1100-XLS?"
python scripts/demo/compare.py "price of ND415A"
python scripts/demo/compare.py "What is the Contoso equivalent of Litware L-9450?"
python scripts/demo/compare.py "My flush valve keeps running and will not shut off. What should I check?"
```

What to point out:

* On the first three questions, `vector` is wrong or unstable and `hybrid` / `semantic` are right.
* On the last one, all four are fine and `semantic` gives the cleanest top result. Hybrid is not a trade-off; it is a superset.

## Step 5: The analyzer matters as much as the mode

Turn off the normalization and try the spaced form:

```bash
python scripts/demo/query.py "What filter does the FX 2200 BR take?" --mode hybrid --no-normalize
python scripts/demo/query.py "What filter does the FX 2200 BR take?" --mode hybrid
```

Without normalization, `FX 2200 BR` is three tokens for the `content` field and does not match `FX-2200-BR` in `part_numbers` (which is one token under the `part_number_exact` analyzer). With normalization, `fx2200br` matches `part_numbers_normalized`. Hybrid search only helps if the keyword leg can actually match the token the user typed. The two questions to ask about any index are: **which analyzer is on the part number field**, and **does the query normalize the way the index does**.

If you cannot change the index, the query side alone still helps: normalize the part number, and add it as a phrase (`"CF-1100-XLS"`) in the search text so that the standard analyzer requires all three tokens adjacent.

## Step 6: Measure it

```bash
python scripts/eval/run_eval.py --mode vector
python scripts/eval/run_eval.py --mode hybrid
python scripts/eval/run_eval.py --mode semantic
python scripts/eval/run_eval.py --compare results/<vector>.json results/<semantic>.json
```

Expect `hit@1` on the `part_lookup` and `part_format` categories to move from roughly a coin flip to nearly all correct, `cross_reference` to move similarly, and `descriptive` to stay high across modes. `stale@1` (top result is archived or community) will still be well above zero; that is module 02.

## What to change in your application

| Setting | Before | After |
|---|---|---|
| Request body | `vectorQueries` only | `search` + `vectorQueries` |
| `queryType` | absent | `semantic`, with `semanticConfiguration` |
| Part numbers in the query | as typed | detected and normalized, appended to `search` |
| Part number field | default analyzer | `keyword_v2` + `lowercase`, plus a normalized copy |
| `k` on the vector query | equal to `top` | 50, so RRF and the reranker have candidates to work with |

The Foundry agent equivalent is the search tool's **Query type** dropdown: `vector` to `vector_semantic_hybrid`.

## References

* [Hybrid search](https://learn.microsoft.com/azure/search/hybrid-search-overview) and [how RRF scoring works](https://learn.microsoft.com/azure/search/hybrid-search-ranking)
* [Semantic ranking](https://learn.microsoft.com/azure/search/semantic-search-overview)
* [Analyzers](https://learn.microsoft.com/azure/search/search-analyzers) and the [Analyze Text API](https://learn.microsoft.com/rest/api/searchservice/indexes/analyze)
