# Setup 3: The Azure AI Search index

The full definition is in [`scripts/setup/index.json`](../../scripts/setup/index.json). `scripts/setup/03_index.py` fills in the index name, semantic configuration name and vector dimensions from `.env` and sends it with a `PUT /indexes/{name}`.

```bash
python scripts/setup/03_index.py --show        # print the definition
python scripts/setup/03_index.py               # create or update
python scripts/setup/03_index.py --recreate    # drop and create (after changing a field type or analyzer)
```

## Fields

| Field | Type | Attributes | Why |
|---|---|---|---|
| `chunk_id` | String | key | `{doc_id}-{strategy}-{nnn}`, deterministic so re-ingestion overwrites instead of duplicating |
| `doc_id` | String | filterable, facetable | Group chunks by document; delete a whole document; evaluation matches on this |
| `chunk_index` | Int32 | filterable, sortable | Order chunks of a document when reconstructing context |
| `title`, `section` | String | searchable, `en.microsoft` | Document title and heading of the section the chunk came from |
| `content` | String | searchable, `en.microsoft` | Chunk text, including the contextual header for structured chunks |
| `content_vector` | Collection(Single) | searchable, `dimensions`, HNSW profile, `stored: false` | Embedding of `content` |
| `brand` | String | searchable, filterable, facetable | Filter or boost by brand |
| `doc_type` | String | filterable, facetable | `spec_sheet`, `install_guide`, `warranty`, `bulletin`, `faq`, `cross_reference`, `service_parts`, `community_post` |
| `status` | String | filterable, facetable | `current`, `archived`, `community` (the key field for module 02) |
| `effective_date` | DateTimeOffset | filterable, sortable, facetable | Freshness boosting and "as of" filters |
| `source` | String | filterable, facetable | `website`, `helpcenter`, `sharepoint`, `archive`, `community` |
| `source_tier` | Int32 | filterable, sortable, facetable | 1 official website to 5 user generated; the grounding prompt prefers lower tiers when passages disagree |
| `is_canonical` | Boolean | filterable, facetable | The copy that is authoritative for this document; filter `is_canonical eq true` drops SharePoint duplicates at older revisions (module 02) |
| `part_numbers` | Collection(String) | searchable, filterable, facetable, analyzer `part_number_exact` | Part numbers as written in the chunk |
| `part_numbers_normalized` | Collection(String) | searchable, filterable, analyzer `part_number_exact` | Same, lowercased with separators removed (`cf1100xls`) |
| `source_url` | String | retrievable | Citation link |
| `content_hash` | String | filterable | Change detection (module 05) |
| `chunking_strategy` | String | filterable, facetable | Lets two strategies coexist during a comparison |
| `last_indexed` | DateTimeOffset | filterable, sortable | Operational visibility |

## The part number analyzer

This is the detail that decides whether "CF-1100-XLS" finds the right document.

```json
"analyzers": [
  {
    "name": "part_number_exact",
    "@odata.type": "#Microsoft.Azure.Search.CustomAnalyzer",
    "tokenizer": "keyword_v2",
    "tokenFilters": [ "lowercase" ]
  }
]
```

With the default `standard.lucene` or `en.microsoft` analyzer, `CF-1100-XLS` becomes three tokens: `cf`, `1100`, `xls`. A query for `CF-1100-XLS` then also matches `CF-1100-XL` (two of three tokens) and `CF-1101-XL` (one token), with scores that are close together. With `keyword_v2` the whole string is one token, so only an exact match scores. `lowercase` keeps it case-insensitive. The normalized field takes care of users who type `cf1100xls` or `CF 1100 XLS`; the query side normalizes the same way (see `scripts/demo/retrieval.py`, `search_text`).

You can test an analyzer without indexing anything:

```http
POST https://<service>.search.windows.net/indexes/contoso-kb/analyze?api-version=2025-09-01
{ "text": "CF-1100-XLS", "analyzer": "en.microsoft" }
```

## Vector search

HNSW with cosine metric, `m: 4`, `efConstruction: 400`, `efSearch: 500`. The defaults are fine for 100 chunks and for 250,000. Dimensions come from `EMBEDDING_DIMENSIONS`; for `text-embedding-3-large` 3072 is native, and 1024 or 1536 work with the `dimensions` request parameter and cut vector storage by half to two thirds with a small quality cost. Decide before ingesting; changing it means `--recreate` and re-ingesting.

The vector field has `stored: false`, so vectors are used for search but never returned, which reduces storage. Set it to true only if you need the vectors back (rare).

## Semantic configuration

```json
"semantic": {
  "defaultConfiguration": "contoso-semantic",
  "configurations": [{
    "name": "contoso-semantic",
    "prioritizedFields": {
      "titleField": { "fieldName": "title" },
      "prioritizedContentFields": [ { "fieldName": "content" } ],
      "prioritizedKeywordsFields": [ { "fieldName": "part_numbers" }, { "fieldName": "brand" }, { "fieldName": "section" } ]
    }
  }]
}
```

The semantic ranker reads these fields when reranking the top 50 results and when generating captions. Two practical consequences: a field that is not listed here is invisible to the reranker even if it is in the index (a common cause of "the price is in the document but the model says it is not available"), and putting `part_numbers` in the keywords list helps the reranker separate look-alike parts.

Semantic ranker must be enabled on the service (*Settings > Semantic ranker*). The Free tier allows 1,000 queries a month, enough for the playbook.

## Scoring profile

```json
"scoringProfiles": [{
  "name": "prefer-current",
  "text": { "weights": { "part_numbers": 5.0, "part_numbers_normalized": 5.0, "title": 2.0, "section": 1.5, "content": 1.0 } },
  "functions": [
    { "type": "tag", "fieldName": "status", "boost": 3.0, "tag": { "tagsParameter": "preferStatus" } },
    { "type": "freshness", "fieldName": "effective_date", "boost": 2.0, "interpolation": "linear", "freshness": { "boostingDuration": "P1095D" } }
  ],
  "functionAggregation": "sum"
}]
```

* **Weights** make a match in `part_numbers` worth five times a match in `content`.
* The **tag** function boosts documents whose `status` equals the value passed at query time (`scoringParameters: ["preferStatus-current"]`).
* The **freshness** function boosts documents with an `effective_date` in the last three years, linearly.

A scoring profile is a soft preference and applies to the text (BM25) side of a hybrid query. Filters are hard exclusions. Module 02 shows when to use which. With a recent API version, `--boosted-reranker` on `03_index.py` adds `"rankingOrder": "boostedRerankerScore"` to the semantic configuration so the profile is also applied after semantic reranking.

## Alternatives worth knowing

* **Integrated vectorization** (a skillset with the Text Split and Azure OpenAI Embedding skills, driven by an indexer) moves chunking and embedding into the search service. It is convenient and keeps up with Blob changes on a schedule, but chunking is less controllable than in module 03 and, in a private network, requires shared private links from the search service to Storage and Azure OpenAI. Module 05 compares the two.
* **A vectorizer on the index** lets you send text in `vectorQueries` (`kind: text`) and have the service embed it. Same network requirement.
* **Knowledge sources and knowledge bases (agentic retrieval)** wrap an index with query planning and multi-query execution for agents. They use the same index; everything in this playbook about fields, analyzers, filters and metadata still applies underneath. Note that agentic retrieval does not apply index scoring profiles.
