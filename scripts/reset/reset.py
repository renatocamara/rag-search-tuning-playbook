"""
Put the environment back to a known state so the demo can be repeated.

    python scripts/reset/reset.py --index            # delete every chunk (keeps the index definition)
    python scripts/reset/reset.py --index --drop     # delete the index itself
    python scripts/reset/reset.py --cosmos           # delete all items in parts and crossReference
    python scripts/reset/reset.py --blobs            # delete every blob in the docs container
    python scripts/reset/reset.py --all              # everything above (index kept, use --drop to remove it)
    python scripts/reset/reset.py --results          # delete local results/*.json

Nothing here touches Azure resources themselves (no resource deletion).
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402


def reset_index(drop):
    if drop:
        common.search_request("DELETE", f"/indexes/{common.SEARCH_INDEX}", ok=(204, 404))
        print(f"index {common.SEARCH_INDEX} deleted")
        return
    keys = [r["chunk_id"] for r in common.search_all_keys(select="chunk_id")]
    for i in range(0, len(keys), 500):
        common.search_delete(keys[i:i + 500])
    print(f"index {common.SEARCH_INDEX}: {len(keys)} chunks deleted, definition kept")


def reset_cosmos():
    from azure.cosmos import CosmosClient
    common.require("COSMOS_ENDPOINT")
    db = CosmosClient(common.COSMOS_ENDPOINT, credential=common.credential()).get_database_client(common.COSMOS_DATABASE)
    for name, pk in ((common.COSMOS_PARTS_CONTAINER, "brand"), (common.COSMOS_XREF_CONTAINER, "competitorBrand")):
        c = db.get_container_client(name)
        n = 0
        for item in list(c.query_items("SELECT c.id, c[@pk] AS pk FROM c", parameters=[{"name": "@pk", "value": pk}],
                                       enable_cross_partition_query=True)):
            c.delete_item(item["id"], partition_key=item["pk"])
            n += 1
        print(f"cosmos {name}: {n} items deleted")


def reset_blobs():
    from azure.storage.blob import BlobServiceClient
    common.require("STORAGE_ACCOUNT")
    svc = BlobServiceClient(f"https://{common.STORAGE_ACCOUNT}.blob.core.windows.net", credential=common.credential())
    container = svc.get_container_client(common.STORAGE_CONTAINER)
    n = 0
    if container.exists():
        for b in container.list_blobs():
            container.delete_blob(b.name)
            n += 1
    print(f"blobs {common.STORAGE_CONTAINER}: {n} deleted")


def reset_results():
    files = glob.glob(os.path.join(common.RESULTS_DIR, "*.json"))
    for f in files:
        os.remove(f)
    print(f"results: {len(files)} files deleted")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--drop", action="store_true")
    ap.add_argument("--cosmos", action="store_true")
    ap.add_argument("--blobs", action="store_true")
    ap.add_argument("--results", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if not any([args.index, args.cosmos, args.blobs, args.results, args.all]):
        ap.print_help()
        sys.exit(1)
    if args.index or args.all:
        reset_index(args.drop)
    if args.cosmos or args.all:
        reset_cosmos()
    if args.blobs or args.all:
        reset_blobs()
    if args.results or args.all:
        reset_results()
