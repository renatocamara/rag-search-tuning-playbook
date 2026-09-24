# Setup 1: Blob Storage, the system of record for documents

## What gets created

One container, `contoso-docs`, with three virtual folders that mirror where content comes from in a real company:

| Folder | Content | Real-world equivalent |
|---|---|---|
| `current/` | 20 official documents: spec sheets, install guides, warranty policy, bulletin, FAQ, cross reference guide, service parts | Current website, product master, SharePoint library |
| `archive/` | 5 superseded documents: 2019 and 2022 spec sheets, 2020 install guide, 2021 warranty policy | Archived website, old PDF library that was never cleaned |
| `community/` | 3 forum threads, two of them with wrong advice | Community forum, Salesforce Community, support tickets |

Every blob carries **metadata** copied from the Markdown front matter (`doc_id`, `brand`, `doc_type`, `status`, `effective_date`, `part_numbers`). This is the single most important thing in the setup: metadata that is present at the source travels with every chunk into the index and makes filtering and boosting possible. When the source cannot carry metadata (a website crawl, for example), the ingestion step has to derive it, from the URL path, the document template or a classifier, and store it anyway.

A document looks like this:

```markdown
---
doc_id: spec-CF-1100-XLS
title: Specification sheet CF-1100-XLS
brand: Contoso Flow
doc_type: spec_sheet
status: current
effective_date: 2024-07-01
part_numbers: ["CF-1100-XLS", "K-CF-1100-RK2", "S-CF-IR3", "B-CF-4AA"]
source_url: https://www.contoso-water.example/current/spec-CF-1100-XLS
---

# AquaSense Sensor Flush Valve 1.28 gpf
...
```

## Steps

1. Make sure your identity has **Storage Blob Data Contributor** on the storage account and that the storage private endpoint resolves from your machine.
2. Set `STORAGE_ACCOUNT` and `STORAGE_CONTAINER` in `.env`.
3. Upload:

    ```bash
    python scripts/setup/01_storage.py
    ```

    Output:

    ```
    created container contoso-docs
      uploaded archive/install-CF-1100-series-2020.md  [archived, install_guide]
      ...
      uploaded current/warranty-policy-2026.md  [current, warranty]
    28 blobs in <account>/contoso-docs
    ```

4. Verify in the portal (*Storage browser > Blob containers > contoso-docs*) that a blob shows its metadata under *Properties*.

## Useful variations

* Upload only official content: `python scripts/setup/01_storage.py --only current`
* Remove one document to simulate a page taken down (module 05): `python scripts/setup/01_storage.py --delete spec-CF-1100-XL-2022`
* Regenerate the documents after editing the generator: `python scripts/data/generate_contoso_data.py`, then upload again (unchanged blobs are simply overwritten).

## Using your own documents

Drop Markdown files with the same front matter into `data/docs/<folder>/`. PDFs and Word files work with the same pipeline once you add a text extraction step in `scripts/setup/04_ingest.py` (for example `pypdf` for text PDFs, or Azure AI Document Intelligence for scanned spec sheets, whose layout model returns tables as Markdown and fits the structured chunker directly).
