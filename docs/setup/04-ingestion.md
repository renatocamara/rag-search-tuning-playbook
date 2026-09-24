# Setup 4: Ingestion (the `/ingest` operation)

`scripts/setup/04_ingest.py` reads documents from Blob Storage, chunks them, extracts part numbers, embeds them and pushes them to the index. It is the playbook's stand-in for the `/ingest` endpoint of an application, and it is where three of the four root causes in the README are either introduced or avoided.

```bash
python scripts/setup/04_ingest.py                          # all sources, structured chunking
python scripts/setup/04_ingest.py --dry-run                # chunk counts only, nothing sent
python scripts/setup/04_ingest.py --source current         # official content only
python scripts/setup/04_ingest.py --chunking naive --force # re-chunk everything with fixed windows (module 03)
python scripts/setup/04_ingest.py --doc spec-CF-1100-XL    # one document
python scripts/setup/04_ingest.py --sync                   # also delete chunks whose blob is gone (module 05)
python scripts/setup/04_ingest.py --from-local             # read data/docs instead of Blob Storage
```

Requires Storage Blob Data Reader, Search Index Data Contributor and Cognitive Services OpenAI User.

## What happens to each document

1. **Read** the blob and parse the front matter into metadata.
2. **Chunk** with the chosen strategy (`scripts/chunking.py`):
    * `naive`: 400-character windows with 60 characters of overlap. Tables get cut, headings get separated from their content.
    * `structured` (default): split on Markdown headings, keep every table whole, further split long sections by paragraph up to 1,200 characters, and prepend a contextual header to each chunk:

        ```
        Document: Specification sheet CF-1100-XLS
        Part numbers: CF-1100-XLS, K-CF-1100-RK2, S-CF-IR3, B-CF-4AA
        Section: Specifications

        | Attribute | Value |
        |---|---|
        | Model | CF-1100-XLS |
        ...
        ```

3. **Extract part numbers** per chunk with a regular expression restricted to numbers that exist in the catalog (so `ASME A112` is not a part). Store them as written and normalized.
4. **Hash** the document text plus the strategy name. If the index already has this document with the same hash and the same number of chunks, skip it. Otherwise delete the old chunks and upload the new ones (`mergeOrUpload`).
5. **Embed** all chunks of the document in one batch call.
6. **Upload** to the index in batches of 100.
7. With `--sync`, after processing, **delete** chunks whose `doc_id` was not seen in the source. This is deletion detection; module 05 explains why it matters.

Sample output for the default run:

```
  indexed bulletin-2024-07-CF-1101-XL           3 chunks  [current, structured]
  indexed cross-reference-guide                 4 chunks  [current, structured]
  ...
  indexed forum-2022-cf1100-repair-kit          1 chunks  [community, structured]

documents indexed: 28, unchanged: 0, chunks produced: 101
index contoso-kb now has 101 chunks (73 current)
```

## Mapping to a production pipeline

| In the script | In an application |
|---|---|
| Blob listing | Event Grid trigger on blob created / deleted, or a scheduled crawl of the website, SharePoint or Salesforce |
| Front matter | Metadata from the CMS, the URL path (`/archive/`), the SharePoint library, the document template, or a small classifier |
| `content_hash` | Same idea; store the hash in the index (as here) or in a table, compare on every run |
| `--sync` | Deletion detection: compare index `doc_id`s with the source listing, or use blob soft delete with an indexer |
| Batch embedding | Same; respect the embedding deployment's tokens-per-minute quota, retry on 429 |
| No cache | Invalidate cached answers whose sources changed (module 05) |

## Chunk size guidance

There is no universal right size. For this kind of content (short technical documents with tables), what works is: sections as the unit, tables never split, a contextual header on every chunk, and an upper bound around 1,000 to 1,500 characters so that five passages fit comfortably in the model's context with room for the answer. Long narrative documents (manuals, legal text) benefit from larger chunks with overlap. Measure with the evaluation set (module 06) rather than guessing.
