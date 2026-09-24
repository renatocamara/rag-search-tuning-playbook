"""
Step 2. Create the Cosmos DB containers and load the structured catalog.

Structured data (part numbers, prices, equivalents, status) belongs in a
database, not in a vector index. Module 04 shows why: an exact lookup by key
is always right, always current and costs nothing to evaluate.

    python scripts/setup/02_cosmos.py            # create database/containers if missing, upsert all items
    python scripts/setup/02_cosmos.py --count    # just print item counts

Containers
  parts            partition key /brand        (data/catalog/parts.json)
  crossReference   partition key /competitorBrand   (data/catalog/cross_reference.json)

Requires: Cosmos DB Built-in Data Contributor (data plane role) on the
account for your identity. The control plane role (Contributor) is not
enough. See docs/setup/02-cosmos-db.md.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
from azure.cosmos import CosmosClient, PartitionKey, exceptions  # noqa: E402


def client():
    common.require("COSMOS_ENDPOINT")
    return CosmosClient(common.COSMOS_ENDPOINT, credential=common.credential())


def ensure_containers(db):
    """Data plane RBAC cannot create databases or containers. If they do not
    exist yet, create them in the portal or with az (see the setup doc) and
    run this script again."""
    try:
        parts = db.get_container_client(common.COSMOS_PARTS_CONTAINER)
        parts.read()
        xref = db.get_container_client(common.COSMOS_XREF_CONTAINER)
        xref.read()
    except exceptions.CosmosResourceNotFoundError:
        common.die(
            f"Database {common.COSMOS_DATABASE} with containers {common.COSMOS_PARTS_CONTAINER} (pk /brand) and "
            f"{common.COSMOS_XREF_CONTAINER} (pk /competitorBrand) must exist. Create them first, see docs/setup/02-cosmos-db.md.")
    return parts, xref


def load():
    db = client().get_database_client(common.COSMOS_DATABASE)
    parts, xref = ensure_containers(db)
    with open(os.path.join(common.DATA_DIR, "catalog", "parts.json"), encoding="utf-8") as f:
        for item in json.load(f):
            parts.upsert_item(item)
    with open(os.path.join(common.DATA_DIR, "catalog", "cross_reference.json"), encoding="utf-8") as f:
        for item in json.load(f):
            xref.upsert_item(item)
    count()


def count():
    db = client().get_database_client(common.COSMOS_DATABASE)
    for name in (common.COSMOS_PARTS_CONTAINER, common.COSMOS_XREF_CONTAINER):
        c = db.get_container_client(name)
        n = list(c.query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))[0]
        print(f"  {common.COSMOS_DATABASE}/{name}: {n} items")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true")
    args = ap.parse_args()
    count() if args.count else load()
