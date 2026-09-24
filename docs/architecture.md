# Architecture

![Contoso RAG reference architecture](../assets/architecture.svg)

## Components and what each one is responsible for

| Component | Role in the solution | What this playbook does with it |
|---|---|---|
| **Blob Storage** | System of record for documents (spec sheets, install guides, warranty policies, bulletins, FAQs, community posts). One container, one folder per source. Every blob carries metadata: `doc_id`, `brand`, `doc_type`, `status`, `effective_date`, `part_numbers`. | `scripts/setup/01_storage.py` uploads `data/docs/**`. `04_ingest.py` reads from here. |
| **Cosmos DB** | System of record for structured product data: the `parts` container (one item per part number: status, price, repair kit, what it replaces) and `crossReference` (competitor part to Contoso part). | `02_cosmos.py` loads `data/catalog/*.json`. Module 04 queries it before searching. |
| **Azure AI Search** | The retrieval engine. One index, `contoso-kb`, holds chunks with a vector, full text, and the metadata above. Configured for hybrid search (BM25 + HNSW vector), semantic ranking, a custom analyzer for part numbers, and a scoring profile that prefers current content. | `03_index.py` creates it from `scripts/setup/index.json`. Every module changes how it is queried or what goes into it. |
| **Azure OpenAI** | `text-embedding-3-large` for embeddings (query and chunks), `gpt-4.1-mini` for grounded answers and as the judge in evaluation. | Called through Entra ID from `scripts/common.py`. |
| **Application** | In production, an API (Function App or Container App behind API Management) with two operations: `/ingest` and `/query`. | Here, Python scripts. `04_ingest.py` is `/ingest`; `demo/query.py` and `demo/lookup.py` are `/query`. The request bodies are printed with `--show-request`. |
| **API Management** | Entry point for the front end (Copilot Studio, Teams, a web app). Authentication, throttling, Content Safety policy. | Not deployed by the playbook; listed because module 07 depends on it. |
| **Managed Redis** | Optional answer or result cache. | Not deployed; module 05 explains why cache invalidation has to be part of the ingestion design. |
| **Log Analytics / Application Insights** | Query logs, latency, token usage. | Not configured by the scripts; evaluation results are written to `results/`. |

## Data flow

### Ingestion (`/ingest`)

1. Read every document from Blob Storage, including its metadata.
2. Chunk it. The strategy is a parameter (`naive` fixed-size windows, or `structured`: split on headings, never inside a table, prepend a contextual header with the document title and part numbers).
3. Extract part numbers mentioned in each chunk and store them twice: as written (`part_numbers`) and normalized (`part_numbers_normalized`, for example `cf1100xls`).
4. Embed the chunk text.
5. Compute a content hash per document. If the hash is unchanged since the last run, skip the document. If it changed, delete the old chunks and upload the new ones. With `--sync`, delete chunks whose source document no longer exists.
6. (Production) Invalidate cached answers that reference the documents that changed.

### Query (`/query`)

1. Detect part numbers in the question. If there are any, look them up in Cosmos DB first (module 04). This resolves status, price, replacement and equivalents with certainty.
2. Build the search request: text query plus vector query (hybrid), semantic configuration, a filter (`status eq 'current'` at minimum, plus brand or doc type when known), and the `prefer-current` scoring profile.
3. Send it to Azure AI Search and take the top passages.
4. Give the model the catalog facts and the passages, with their `doc_id`, `status` and `effective_date`, and ask for an answer that cites its sources and prefers current documents.

## Network and identity

* All five services have **private endpoints** in the landing zone spoke. DNS resolution goes through the private DNS zones linked in the hub. The scripts run from a machine inside that network (jump box, VPN client, or a Container App job).
* Azure AI Search uses **shared private links** to reach Azure OpenAI (if you use integrated vectorization or a vectorizer) and Cosmos DB / Storage (if you use indexers, see module 05). The push model used by the scripts does not need them: the application does the embedding and the reading.
* **Identity**: the scripts use `DefaultAzureCredential`. On a laptop that is `az login`; in an app it is the managed identity. Required roles are listed in [prerequisites.md](prerequisites.md). No API keys are used or stored.
* `scripts/pre_demo_check.py` verifies that every hostname resolves to a private address before a demo.

## Why the index looks the way it does

| Design choice | Reason |
|---|---|
| One index for all sources, with `status` and `doc_type` fields | Filtering at query time is cheaper and more flexible than separate indexes, and lets you run "what would the answer be if archive were excluded" as an experiment. |
| `part_numbers` with a custom analyzer (`keyword_v2` tokenizer + `lowercase`) | Standard analyzers split `CF-1100-XLS` into `cf`, `1100`, `xls`, which also match `CF-1100-XL`. The keyword tokenizer keeps the whole string as one token. Lowercasing makes the match case-insensitive. |
| `part_numbers_normalized` | Users type `cf1100xls` or `CF 1100 XLS`. The query side normalizes the same way, so all forms hit. |
| Contextual header in every chunk | A chunk with "Repair kit: K-CF-1100-RK2" is useless unless it also says which product the table belongs to. |
| `effective_date` sortable and filterable | Freshness boosting and "as of" questions. |
| Scoring profile `prefer-current` | A soft preference for current documents and recent effective dates when a filter is not appropriate (for example, a rep asking about a discontinued product still needs the archived sheet). |
| Semantic configuration with `part_numbers`, `brand`, `section` as keywords | The semantic ranker uses these fields for captions and reranking; putting the part number there matters for look-alike disambiguation. |
| Vector field with `stored: false` | Vectors are needed for search, not for display; not storing them roughly halves index size. Dimensions are configurable (`EMBEDDING_DIMENSIONS`) because 1024 or 1536 dimensions of `text-embedding-3-large` are usually indistinguishable in retrieval quality on this kind of content and much cheaper. |
