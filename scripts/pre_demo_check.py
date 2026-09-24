"""
Run this five minutes before a demo. It checks, in order:

  1. .env is complete
  2. the Search, Azure OpenAI, Storage and Cosmos hostnames resolve to PRIVATE addresses
     (a public IP means you are not on the VPN, or the private DNS zone is not linked)
  3. your identity can get tokens
  4. the index exists and has chunks (and how many per status)
  5. embeddings and chat completions respond
  6. Cosmos containers have items

    python scripts/pre_demo_check.py
"""

import ipaddress
import os
import socket
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402

OK, WARN, FAIL = "  [ok]  ", "  [warn]", "  [FAIL]"


def check_dns(label, url):
    if not url:
        print(f"{WARN} {label}: not configured")
        return
    host = urlparse(url if "://" in url else f"https://{url}").hostname
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror as e:
        print(f"{FAIL} {label}: {host} does not resolve ({e})")
        return
    private = ipaddress.ip_address(ip).is_private
    print(f"{OK if private else WARN} {label}: {host} -> {ip} ({'private' if private else 'PUBLIC'})")


def main():
    print("\n1. settings")
    for name in ("SEARCH_ENDPOINT", "SEARCH_INDEX", "AOAI_ENDPOINT", "EMBEDDING_DEPLOYMENT", "CHAT_DEPLOYMENT",
                 "STORAGE_ACCOUNT", "COSMOS_ENDPOINT"):
        val = getattr(common, name)
        print(f"{OK if val else FAIL} {name} = {val or '(missing)'}")

    print("\n2. name resolution (expect private addresses when everything is behind private endpoints)")
    check_dns("search", common.SEARCH_ENDPOINT)
    check_dns("azure openai", common.AOAI_ENDPOINT)
    check_dns("storage", f"https://{common.STORAGE_ACCOUNT}.blob.core.windows.net" if common.STORAGE_ACCOUNT else "")
    check_dns("cosmos", common.COSMOS_ENDPOINT)

    print("\n3. identity")
    try:
        common.credential().get_token("https://search.azure.com/.default")
        print(f"{OK} token for Azure AI Search")
        common.credential().get_token("https://cognitiveservices.azure.com/.default")
        print(f"{OK} token for Azure OpenAI")
    except Exception as e:
        print(f"{FAIL} could not get a token: {e}\n        run: az login")
        return

    print("\n4. index")
    try:
        total = common.search_count()
        by_status = {s: common.search_count(filter_expr=f"status eq '{s}'") for s in ("current", "archived", "community")}
        strategies = common.search_query({"search": "*", "top": 0, "facets": ["chunking_strategy"]}).get("@search.facets", {})
        strat = ", ".join(f"{f['value']}={f['count']}" for f in strategies.get("chunking_strategy", []))
        print(f"{OK if total else WARN} {common.SEARCH_INDEX}: {total} chunks  {by_status}  chunking: {strat or '-'}")
    except SystemExit:
        print(f"{FAIL} index not reachable or missing. Run scripts/setup/03_index.py and 04_ingest.py")

    print("\n5. models")
    try:
        v = common.embed("hello")[0]
        print(f"{OK} embeddings: {common.EMBEDDING_DEPLOYMENT} returned {len(v)} dimensions "
              f"({'matches' if len(v) == common.EMBEDDING_DIMENSIONS else 'DOES NOT MATCH'} EMBEDDING_DIMENSIONS={common.EMBEDDING_DIMENSIONS})")
        common.chat("Reply with the single word OK.", "ping")
        print(f"{OK} chat: {common.CHAT_DEPLOYMENT} responded")
    except Exception as e:
        print(f"{FAIL} model call failed: {str(e)[:200]}")

    print("\n6. cosmos")
    try:
        from azure.cosmos import CosmosClient
        db = CosmosClient(common.COSMOS_ENDPOINT, credential=common.credential()).get_database_client(common.COSMOS_DATABASE)
        for name in (common.COSMOS_PARTS_CONTAINER, common.COSMOS_XREF_CONTAINER):
            n = list(db.get_container_client(name).query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))[0]
            print(f"{OK if n else WARN} {name}: {n} items")
    except Exception as e:
        print(f"{FAIL} cosmos: {str(e)[:200]}")
    print()


if __name__ == "__main__":
    main()
