"""
Structured lookup first, search second (module 04).

When a question contains a part number, the right first move is an exact
lookup in the system of record (Cosmos DB), not a similarity search. The
catalog answers "what kit fits X", "is X discontinued", "what replaces X",
"what is the Contoso equivalent of competitor part Y" with certainty. The
search index is then queried with a filter on that part number to bring back
the supporting document text for the model to explain.

    python scripts/demo/lookup.py "What repair kit fits the CF-1100-XLS?"
    python scripts/demo/lookup.py "Is CF-1101-XL still available?"
    python scripts/demo/lookup.py "Contoso equivalent for Litware L-9450"
    python scripts/demo/lookup.py "price of nd415a"
    python scripts/demo/lookup.py "..." --answer
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402
import retrieval  # noqa: E402
from azure.cosmos import CosmosClient  # noqa: E402


def cosmos():
    common.require("COSMOS_ENDPOINT")
    db = CosmosClient(common.COSMOS_ENDPOINT, credential=common.credential()).get_database_client(common.COSMOS_DATABASE)
    return db.get_container_client(common.COSMOS_PARTS_CONTAINER), db.get_container_client(common.COSMOS_XREF_CONTAINER)


def lookup_part(parts_container, norm):
    # Normalized comparison on the server side keeps 'nd415a' and 'ND-415-A' equal.
    q = "SELECT * FROM c WHERE LOWER(REPLACE(c.id, '-', '')) = @n"
    rows = list(parts_container.query_items(q, parameters=[{"name": "@n", "value": norm}], enable_cross_partition_query=True))
    return rows[0] if rows else None


def lookup_xref(xref_container, norm):
    q = "SELECT * FROM c WHERE LOWER(REPLACE(c.competitorPartNumber, '-', '')) = @n"
    rows = list(xref_container.query_items(q, parameters=[{"name": "@n", "value": norm}], enable_cross_partition_query=True))
    return rows[0] if rows else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--answer", action="store_true")
    ap.add_argument("--top", type=int, default=4)
    args = ap.parse_args()

    parts_c, xref_c = cosmos()
    # No `known` filter here on purpose: the catalog itself decides what is a part number.
    candidates = common.extract_part_numbers(args.question)
    facts, resolved = [], []
    for norm, display in candidates.items():
        part = lookup_part(parts_c, norm)
        if part:
            resolved.append(part["id"])
            line = f"{part['id']}: {part['name']} | status={part['status']} | list price ${part['listPrice']:,.2f}"
            for k in ("repairKit", "filter", "strainer", "sensorModule", "batteryPack", "powerSupply", "replacedBy", "replaces", "discontinuedDate", "fits"):
                if k in part:
                    line += f" | {k}={part[k]}"
            facts.append(line)
            continue
        x = lookup_xref(xref_c, norm)
        if x:
            resolved.append(x["contosoPartNumber"])
            facts.append(f"{x['competitorBrand']} {x['competitorPartNumber']} ({x['competitorDescription']}) -> "
                         f"Contoso {x['contosoPartNumber']} [{x['matchType']}] {x.get('notes', '')}")

    print(f"\nQ: {args.question}")
    print(f"part numbers detected: {', '.join(candidates.values()) or 'none'}")
    print("\n--- 1. Structured lookup (Cosmos DB) ---")
    for f in facts or ["  no catalog match"]:
        print(f"  {f}")

    print("\n--- 2. Search, filtered to the resolved part numbers ---")
    filter_expr = None
    if resolved:
        ors = " or ".join(f"part_numbers/any(p: p eq '{p}')" for p in sorted(set(resolved)))
        filter_expr = f"({ors}) and status eq 'current'"
    _, rows = retrieval.run(args.question, "semantic", top=args.top, filter_expr=filter_expr)
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['doc_id']:38s} {r['section'][:30]:30s} [{r['status']}]")

    if args.answer:
        print("\n--- 3. Grounded answer (catalog facts + passages) ---")
        if facts:
            rows.insert(0, {"doc_id": "cosmos:catalog", "status": "current", "doc_type": "catalog",
                            "effective_date": "", "content": "\n".join(facts)})
        print(retrieval.answer(args.question, rows))
    print()


if __name__ == "__main__":
    main()
