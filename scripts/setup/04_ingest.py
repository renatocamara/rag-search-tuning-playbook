"""
Step 4. Ingest documents from Blob Storage into the index (push model).

This script plays the role of an application's /ingest endpoint: read the
source, chunk it, embed it, push it. It is deliberately explicit so that every
decision that affects retrieval quality is visible:

  * which sources go into the index               --source
  * how documents are chunked                     --chunking naive | structured
  * what metadata travels with every chunk         (brand, doc_type, status, effective_date, part_numbers)
  * how changes and deletions are detected         content_hash per document, --sync

Examples
    python scripts/setup/04_ingest.py                              # everything, structured chunking
    python scripts/setup/04_ingest.py --source current             # only official current content
    python scripts/setup/04_ingest.py --chunking naive --force     # re-chunk everything the naive way (module 03)
    python scripts/setup/04_ingest.py --doc spec-CF-1100-XL        # one document
    python scripts/setup/04_ingest.py --sync                       # remove index chunks whose blob is gone (module 05)
    python scripts/setup/04_ingest.py --from-local                 # read data/docs instead of Blob (no storage needed)

Requires: Storage Blob Data Reader, Search Index Data Contributor,
Cognitive Services OpenAI User.
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import chunking  # noqa: E402


def read_sources(from_local, sources):
    """Yield (folder, name, text) for every Markdown document."""
    if from_local:
        root = os.path.join(common.DATA_DIR, "docs")
        for folder in sorted(os.listdir(root)):
            if folder not in sources:
                continue
            for name in sorted(os.listdir(os.path.join(root, folder))):
                with open(os.path.join(root, folder, name), encoding="utf-8") as f:
                    yield folder, name, f.read()
        return
    from azure.storage.blob import BlobServiceClient
    common.require("STORAGE_ACCOUNT")
    svc = BlobServiceClient(f"https://{common.STORAGE_ACCOUNT}.blob.core.windows.net", credential=common.credential())
    container = svc.get_container_client(common.STORAGE_CONTAINER)
    for blob in container.list_blobs():
        folder, _, name = blob.name.partition("/")
        if folder not in sources or not name.endswith(".md"):
            continue
        text = container.download_blob(blob.name).readall().decode("utf-8")
        yield folder, name, text


def build_chunks(meta, body, strategy, known_parts):
    doc_id = meta["doc_id"]
    # The contextual header carries only the document's own part numbers (front matter).
    # Part numbers merely mentioned in the text (for example "replaces CF-1101-XL") are
    # picked up per chunk below, so they do not leak into every chunk of the document.
    parts = list(meta.get("part_numbers", []))
    pieces = chunking.chunk(body, strategy, title=meta.get("title", doc_id), part_numbers=parts)
    doc_hash = common.content_hash(body + strategy)
    docs = []
    for c in pieces:
        # part numbers present in THIS chunk (plus the document level list for structured chunks,
        # because the contextual header already carries them)
        in_chunk = common.extract_part_numbers(c["text"], known_parts)
        chunk_parts = sorted(set(in_chunk.values()))
        docs.append({
            "chunk_id": f"{doc_id}-{strategy}-{c['index']:03d}",
            "doc_id": doc_id,
            "chunk_index": c["index"],
            "title": meta.get("title", doc_id),
            "section": c["section"],
            "content": c["text"],
            "brand": meta.get("brand", ""),
            "doc_type": meta.get("doc_type", ""),
            "status": meta.get("status", ""),
            "effective_date": f"{meta.get('effective_date', '2000-01-01')}T00:00:00Z",
            "part_numbers": chunk_parts,
            "part_numbers_normalized": [common.normalize_part_number(p) for p in chunk_parts],
            "source_url": meta.get("source_url", ""),
            "content_hash": doc_hash,
            "chunking_strategy": strategy,
            "last_indexed": common.now_iso(),
        })
    return docs, doc_hash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", nargs="*", default=["current", "archive", "community"],
                    choices=["current", "archive", "community"])
    ap.add_argument("--chunking", default="structured", choices=["naive", "structured"])
    ap.add_argument("--doc", help="ingest only this doc_id")
    ap.add_argument("--force", action="store_true", help="re-index even if content_hash is unchanged")
    ap.add_argument("--sync", action="store_true", help="delete index chunks whose source document no longer exists")
    ap.add_argument("--from-local", action="store_true", help="read data/docs instead of Blob Storage")
    ap.add_argument("--dry-run", action="store_true", help="chunk and print counts, do not embed or upload")
    args = ap.parse_args()

    known_parts = common.known_parts()

    # What is in the index today (for change detection and --sync)
    existing = defaultdict(list)
    if not args.dry_run:
        for row in common.search_all_keys(select="chunk_id,doc_id,content_hash,status"):
            existing[row["doc_id"]].append(row)

    seen, uploaded, skipped, total_chunks = set(), 0, 0, 0
    for folder, name, text in read_sources(args.from_local, args.source):
        meta, body = common.parse_front_matter(text)
        doc_id = meta.get("doc_id") or name.rsplit(".", 1)[0]
        if args.doc and doc_id != args.doc:
            continue
        seen.add(doc_id)
        docs, doc_hash = build_chunks(meta, body, args.chunking, known_parts)
        total_chunks += len(docs)
        if args.dry_run:
            print(f"  {doc_id:40s} {len(docs):3d} chunks  [{meta.get('status')}, {meta.get('doc_type')}]")
            continue
        current = existing.get(doc_id, [])
        if current and not args.force and all(r.get("content_hash") == doc_hash for r in current) \
                and len(current) == len(docs):
            skipped += 1
            continue
        # Replace the document atomically enough for a demo: delete old chunks, upload new ones.
        if current:
            common.search_delete([r["chunk_id"] for r in current])
        texts = [d["content"] for d in docs]
        vectors = common.embed(texts)
        for d, v in zip(docs, vectors):
            d["content_vector"] = v
        common.search_upload(docs)
        uploaded += 1
        print(f"  indexed {doc_id:40s} {len(docs):3d} chunks  [{meta.get('status')}, {args.chunking}]")

    if args.sync and not args.dry_run and not args.doc:
        # Deletion detection: anything in the index that is not in the source anymore goes away.
        # Only documents within the selected --source folders are considered, so that
        # "--source current --sync" does not delete archive chunks you ingested on purpose.
        status_of = {"current": "current", "archive": "archived", "community": "community"}
        selected = {status_of[s] for s in args.source}
        gone = [doc_id for doc_id, rows in existing.items()
                if doc_id not in seen and rows and rows[0].get("status") in selected]
        for doc_id in gone:
            common.search_delete([r["chunk_id"] for r in existing[doc_id]])
            print(f"  removed {doc_id} ({len(existing[doc_id])} chunks): source no longer exists")

    print(f"\ndocuments indexed: {uploaded}, unchanged: {skipped}, chunks produced: {total_chunks}")
    if not args.dry_run:
        total = common.search_count()
        current = common.search_count(filter_expr="status eq 'current'")
        print(f"index {common.SEARCH_INDEX} now has {total} chunks ({current} current)")


if __name__ == "__main__":
    main()
