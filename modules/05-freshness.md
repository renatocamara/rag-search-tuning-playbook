# Module 05: Freshness (changed documents, deleted documents, caches)

**Symptom at Contoso:** the warranty policy changed on January 1. In March a rep asks and gets the old terms. The web team says the page was updated in January. The search team says the index was rebuilt last weekend. Both are right: the new page was indexed, and the old page's chunks were never removed, and the answer for that question had been cached since February.

**Root cause:** "we re-index weekly" describes a frequency, not a mechanism. Three separate mechanisms decide whether an answer is current: change detection (did a changed document replace its old chunks?), deletion detection (did a removed document leave the index?), and cache invalidation (does a cached answer know its sources changed?). A scheduled full crawl handles only the first, and only if the chunk keys are deterministic.

**Fix:** deterministic chunk ids, a content hash per document, a sync step that deletes orphans, and cache keys tied to the documents that produced the answer.

Time: 10 minutes.

## Step 1: A changed document

Edit one fact in a current document and re-ingest:

```bash
# change the list price in the CF-1100-XL spec sheet
sed -i 's/\$412.00/\$419.00/' data/docs/current/spec-CF-1100-XL.md         # Windows: edit the file by hand
python scripts/setup/01_storage.py --only current                            # upload
python scripts/setup/04_ingest.py --source current                           # only the changed document is re-indexed
python scripts/demo/query.py "What is the list price of the CF-1100-XL?" --mode semantic --current
```

The ingestion output shows one document indexed and 27 unchanged. The `content_hash` per document is what makes that possible: re-running ingestion over the whole source costs one listing and one hash comparison per document, and embedding only what changed. The old chunks of the changed document are deleted before the new ones are uploaded, so there is never a moment with both prices in the index.

Restore the file afterwards with `python scripts/data/generate_contoso_data.py` and re-upload.

## Step 2: A deleted document

Contoso finally takes the 2022 archived sheet off the site:

```bash
python scripts/setup/01_storage.py --delete spec-CF-1100-XL-2022
python scripts/setup/04_ingest.py                     # without --sync: nothing happens to the index
python scripts/demo/query.py "repair kit for CF-1100-XL" --mode semantic    # the 2022 sheet is still there
python scripts/setup/04_ingest.py --sync              # orphan chunks removed
```

Output of the sync:

```
  removed spec-CF-1100-XL-2022 (4 chunks): source no longer exists
```

This is the failure that lets stale content survive for years: a crawl adds and updates, and nothing ever deletes. With deterministic `chunk_id`s (`{doc_id}-{strategy}-{nnn}`), the sync is a set difference between the `doc_id`s in the index and the `doc_id`s in the source.

If you use an Azure AI Search **indexer** instead of a push pipeline, the equivalent is deletion detection on the data source: native blob soft delete (the indexer removes documents whose blob was soft-deleted within the retention window) or a soft-delete metadata column (`IsDeleted = true`). Without one of those configured, an indexer also never deletes. For Cosmos DB sources, the change feed via the `_ts` high water mark detects updates but not deletions, so the soft-delete column is required there too.

## Step 3: The cache

Contoso's architecture has Managed Redis in front of `/query`. Caching the final answer for a normalized question is a large latency and cost win for the top 200 questions. It is also where a fixed index still serves stale answers.

The rule: **a cached answer must be invalidated when any document it cited changes or is deleted.** The ingestion step knows exactly which `doc_id`s changed (it hashed them) and which were removed (it synced them). Two workable designs:

| Design | How | Trade-off |
|---|---|---|
| Cache key includes an index version | Ingestion increments a version number (a Redis key, or the index's own `last_indexed` max). `/query` reads the version and uses it in the cache key. | Simple; every ingestion run invalidates everything, even when one document changed. Fine for weekly runs. |
| Reverse index of `doc_id` to cache keys | When storing an answer, also add its cache key to a Redis set per cited `doc_id`. Ingestion deletes the sets for changed or removed documents. | Precise; a price change only evicts answers that cited that spec sheet. A little more code. |

Either is better than a TTL alone. A TTL of one day means up to one day of wrong answers after every change, and no one will know which answers were wrong.

The scripts do not use a cache. To see the effect, note the `last_indexed` field in the index: it is the timestamp to compare a cached answer against.

## Step 4: Frequency

With the three mechanisms in place, frequency becomes a business decision per source rather than a global setting:

| Source | Change rate | Suggested cadence | Trigger |
|---|---|---|---|
| Product catalog (Cosmos DB) | daily prices, occasional discontinuations | nightly | scheduled job from the product master |
| Bulletins, warranty policy | rare, high impact | on publish | Event Grid on the blob, or a "publish" button in the CMS calling `/ingest` for one document |
| Spec sheets, install guides | monthly | weekly, plus on publish | scheduled crawl with hash comparison |
| Community content | constant, low value | do not index, or monthly with `status = community` | |
| Archived site | never changes | index once with `status = archived`, or not at all | |

A weekly full crawl is a fine backstop. It is not a freshness strategy for the documents that matter most, because those change rarely and matter immediately.

## Push pipeline versus indexer

| | Push (this playbook, `/ingest`) | Indexer with integrated vectorization |
|---|---|---|
| Chunking | your code, tables kept whole, contextual headers | Text Split skill, fixed size, no table awareness |
| Metadata | from any source, any logic | from blob metadata and skill outputs |
| Change detection | content hash | blob `LastModified` |
| Deletion | `--sync` set difference | requires soft delete configuration |
| Private network | application reaches services through private endpoints; no shared private links needed | search service needs shared private links to Storage and Azure OpenAI, and `executionEnvironment: private` |
| Operations | you run it (Function timer, Container App job) | managed schedule, portal visibility |

Both are valid. The push model gives control over the two things that decided modules 02 and 03 (metadata and chunking), which is why the playbook uses it.

## What to change in your application

| Setting | Before | After |
|---|---|---|
| Chunk ids | generated (GUID) per run | deterministic `{doc_id}-{strategy}-{n}` |
| Change detection | none, full re-embed weekly | content hash per document, embed only changes |
| Deletion | none | sync step (push) or soft delete (indexer) |
| Cache | TTL | invalidated by ingestion, per cited document or per index version |
| Cadence | one weekly job | per source, event driven for high impact documents, weekly backstop |

## References

* [Change and deletion detection for blobs](https://learn.microsoft.com/azure/search/search-howto-index-changed-deleted-blobs)
* [Cosmos DB indexer and the change feed](https://learn.microsoft.com/azure/search/search-howto-index-cosmosdb)
* [Indexer schedules](https://learn.microsoft.com/azure/search/search-howto-schedule-indexers)
* [Shared private links for indexers](https://learn.microsoft.com/azure/search/search-indexer-howto-access-private)
