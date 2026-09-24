"""
Step 3. Create (or recreate) the Azure AI Search index from scripts/setup/index.json.

    python scripts/setup/03_index.py                  # create if missing, otherwise update in place
    python scripts/setup/03_index.py --recreate       # drop and create (needed when field types change)
    python scripts/setup/03_index.py --show           # print the definition that would be sent
    python scripts/setup/03_index.py --boosted-reranker
        # adds "rankingOrder": "boostedRerankerScore" to the semantic configuration so
        # scoring profiles are applied after semantic reranking (requires a recent API version)

Requires: Search Service Contributor on the search service.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402


def definition(boosted_reranker=False):
    with open(os.path.join(os.path.dirname(__file__), "index.json"), encoding="utf-8") as f:
        raw = f.read()
    raw = (raw.replace("__INDEX_NAME__", common.SEARCH_INDEX)
              .replace('"__DIMENSIONS__"', str(common.EMBEDDING_DIMENSIONS))
              .replace("__SEMANTIC_CONFIG__", common.SEMANTIC_CONFIG))
    idx = json.loads(raw)
    if boosted_reranker:
        for cfg in idx["semantic"]["configurations"]:
            cfg["rankingOrder"] = "boostedRerankerScore"
    return idx


def exists():
    import requests
    url = f"{common.SEARCH_ENDPOINT}/indexes/{common.SEARCH_INDEX}"
    token = common.credential().get_token("https://search.azure.com/.default").token
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     params={"api-version": common.SEARCH_API_VERSION}, timeout=30)
    return r.status_code == 200


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--boosted-reranker", action="store_true")
    args = ap.parse_args()

    idx = definition(args.boosted_reranker)
    if args.show:
        common.print_json(idx)
        sys.exit(0)

    if args.recreate and exists():
        common.search_request("DELETE", f"/indexes/{common.SEARCH_INDEX}")
        print(f"deleted index {common.SEARCH_INDEX}")

    # PUT creates or updates. Adding fields is fine in place; changing a field's
    # type or analyzer requires --recreate.
    common.search_request("PUT", f"/indexes/{common.SEARCH_INDEX}", idx)
    print(f"index {common.SEARCH_INDEX} ready ({common.EMBEDDING_DIMENSIONS} dimensions, "
          f"semantic config {common.SEMANTIC_CONFIG}, scoring profile prefer-current)")
