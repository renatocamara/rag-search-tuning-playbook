"""
Step 1. Upload the Contoso documents to Blob Storage.

Blob Storage is the system of record for content, exactly as a company
website crawl or a SharePoint export would be. Each blob carries metadata
(brand, doc_type, status, effective_date) taken from the Markdown front
matter, so the ingestion step never has to guess.

    python scripts/setup/01_storage.py              # upload data/docs/** (current, archive, community)
    python scripts/setup/01_storage.py --only current
    python scripts/setup/01_storage.py --delete spec-CF-1100-XL-2022   # remove one blob (freshness demo)

Requires: Storage Blob Data Contributor on the storage account.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
from azure.storage.blob import BlobServiceClient, ContentSettings  # noqa: E402


def client():
    common.require("STORAGE_ACCOUNT")
    svc = BlobServiceClient(f"https://{common.STORAGE_ACCOUNT}.blob.core.windows.net", credential=common.credential())
    container = svc.get_container_client(common.STORAGE_CONTAINER)
    if not container.exists():
        container.create_container()
        print(f"created container {common.STORAGE_CONTAINER}")
    return container


def upload(only=None):
    container = client()
    root = os.path.join(common.DATA_DIR, "docs")
    n = 0
    for folder in sorted(os.listdir(root)):
        if only and folder not in only:
            continue
        for name in sorted(os.listdir(os.path.join(root, folder))):
            path = os.path.join(root, folder, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            meta, _ = common.parse_front_matter(text)
            blob_name = f"{folder}/{name}"
            metadata = {k: str(meta.get(k, "")) for k in ("doc_id", "brand", "doc_type", "status", "effective_date")}
            metadata["part_numbers"] = ",".join(meta.get("part_numbers", []))
            container.upload_blob(blob_name, text.encode("utf-8"), overwrite=True, metadata=metadata,
                                  content_settings=ContentSettings(content_type="text/markdown"))
            n += 1
            print(f"  uploaded {blob_name}  [{metadata['status']}, {metadata['doc_type']}]")
    print(f"{n} blobs in {common.STORAGE_ACCOUNT}/{common.STORAGE_CONTAINER}")


def delete(doc_id):
    container = client()
    deleted = 0
    for blob in container.list_blobs():
        if blob.name.endswith(f"/{doc_id}.md"):
            container.delete_blob(blob.name)
            print(f"  deleted {blob.name}")
            deleted += 1
    if not deleted:
        print(f"no blob found for doc_id {doc_id}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=["current", "archive", "community"], help="upload only these folders")
    ap.add_argument("--delete", metavar="DOC_ID", help="delete the blob for this doc_id instead of uploading")
    args = ap.parse_args()
    if args.delete:
        delete(args.delete)
    else:
        upload(args.only)
