"""
Shared helpers for every script in this playbook.

Design choices, on purpose:
  * REST calls to Azure AI Search instead of the SDK, so the JSON you see in
    the terminal is exactly the JSON an application (for example an Azure
    Function behind /query) would send. Copy it into your own code.
  * Entra ID (managed identity or your own login) everywhere. No keys.
  * Everything is configured through .env (see .env.example).
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT", "").rstrip("/")
SEARCH_INDEX = os.getenv("SEARCH_INDEX", "contoso-kb")
SEARCH_API_VERSION = os.getenv("SEARCH_API_VERSION", "2025-09-01")
SEMANTIC_CONFIG = os.getenv("SEMANTIC_CONFIG", "contoso-semantic")

# The OpenAI-compatible endpoint of the Foundry (AI Services) account, e.g.
# https://<account>.openai.azure.com. Base URL only: the SDK adds /openai/... itself.
AOAI_ENDPOINT = os.getenv("AOAI_ENDPOINT", "").rstrip("/")
for _suffix in ("/openai/v1", "/openai"):
    if AOAI_ENDPOINT.endswith(_suffix):
        AOAI_ENDPOINT = AOAI_ENDPOINT[: -len(_suffix)]
AOAI_API_VERSION = os.getenv("AOAI_API_VERSION", "2025-04-01-preview")
EMBEDDING_DEPLOYMENT = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))
CHAT_DEPLOYMENT = os.getenv("CHAT_DEPLOYMENT", "gpt-4.1-mini")

STORAGE_ACCOUNT = os.getenv("STORAGE_ACCOUNT", "")
STORAGE_CONTAINER = os.getenv("STORAGE_CONTAINER", "contoso-docs")

COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT", "").rstrip("/")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "ContosoCatalog")
COSMOS_PARTS_CONTAINER = os.getenv("COSMOS_PARTS_CONTAINER", "parts")
COSMOS_XREF_CONTAINER = os.getenv("COSMOS_XREF_CONTAINER", "crossReference")

DATA_DIR = os.path.join(ROOT, "data")
RESULTS_DIR = os.path.join(ROOT, "results")

_credential = None


def credential():
    global _credential
    if _credential is None:
        # Works with: az login (developer laptop over VPN), managed identity
        # (Function App, VM, Container App), or environment variables.
        _credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return _credential


def require(*names):
    missing = [n for n in names if not globals().get(n)]
    if missing:
        die(f"Missing settings in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Azure AI Search REST
# ---------------------------------------------------------------------------

def _search_headers():
    token = credential().get_token("https://search.azure.com/.default").token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def search_request(method, path, body=None, params=None, ok=(200, 201, 204, 207)):
    require("SEARCH_ENDPOINT")
    url = f"{SEARCH_ENDPOINT}{path}"
    params = dict(params or {})
    params.setdefault("api-version", SEARCH_API_VERSION)
    resp = requests.request(method, url, headers=_search_headers(), params=params,
                            data=json.dumps(body) if body is not None else None, timeout=60)
    if resp.status_code not in ok:
        die(f"{method} {path} returned {resp.status_code}: {resp.text[:800]}")
    if resp.text:
        try:
            return resp.json()
        except ValueError:
            return resp.text
    return None


def search_query(body, index=None):
    """POST /indexes/{index}/docs/search. Returns the raw response."""
    index = index or SEARCH_INDEX
    return search_request("POST", f"/indexes/{index}/docs/search", body)


def search_upload(documents, index=None, batch_size=100):
    index = index or SEARCH_INDEX
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        body = {"value": [dict(d, **{"@search.action": "mergeOrUpload"}) for d in batch]}
        search_request("POST", f"/indexes/{index}/docs/index", body)


def search_delete(keys, key_field="chunk_id", index=None):
    index = index or SEARCH_INDEX
    if not keys:
        return
    body = {"value": [{"@search.action": "delete", key_field: k} for k in keys]}
    search_request("POST", f"/indexes/{index}/docs/index", body)


def search_count(index=None, filter_expr=None):
    body = {"search": "*", "count": True, "top": 0}
    if filter_expr:
        body["filter"] = filter_expr
    return search_query(body, index).get("@odata.count", 0)


def search_all_keys(select="chunk_id,doc_id,content_hash", filter_expr=None, index=None):
    """Page through the index and return the selected fields for every chunk."""
    out, skip, page = [], 0, 1000
    while True:
        body = {"search": "*", "select": select, "top": page, "skip": skip, "orderby": "chunk_id"}
        if filter_expr:
            body["filter"] = filter_expr
        res = search_query(body, index).get("value", [])
        out.extend(res)
        if len(res) < page:
            return out
        skip += page


# ---------------------------------------------------------------------------
# Azure OpenAI (embeddings and chat)
# ---------------------------------------------------------------------------

_aoai = None


def aoai():
    global _aoai
    if _aoai is None:
        from openai import AzureOpenAI
        require("AOAI_ENDPOINT")
        provider = get_bearer_token_provider(credential(), "https://cognitiveservices.azure.com/.default")
        _aoai = AzureOpenAI(azure_endpoint=AOAI_ENDPOINT, azure_ad_token_provider=provider,
                            api_version=AOAI_API_VERSION)
    return _aoai


def embed(texts, batch_size=64):
    """Embed a list of strings. Returns a list of vectors."""
    if isinstance(texts, str):
        texts = [texts]
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        kwargs = {"model": EMBEDDING_DEPLOYMENT, "input": batch}
        # text-embedding-3-* accept a dimensions parameter (Matryoshka). Leave it
        # out for older models such as text-embedding-ada-002.
        if EMBEDDING_DEPLOYMENT.startswith("text-embedding-3"):
            kwargs["dimensions"] = EMBEDDING_DIMENSIONS
        for attempt in range(5):
            try:
                res = aoai().embeddings.create(**kwargs)
                break
            except Exception as e:  # throttling
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
                print(f"  embedding retry {attempt + 1}: {e}")
        vectors.extend([d.embedding for d in res.data])
    return vectors


def chat(system, user, temperature=None):
    """Chat completion against the deployment in CHAT_DEPLOYMENT.
    temperature is only sent when given: reasoning models (gpt-5 family, o-series)
    reject any value other than the default."""
    kwargs = {
        "model": CHAT_DEPLOYMENT,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    res = aoai().chat.completions.create(**kwargs)
    return res.choices[0].message.content


# ---------------------------------------------------------------------------
# Part numbers
# ---------------------------------------------------------------------------

# Contoso part numbers look like CF-1100-XLS, K-CF-1100-RK2, ND-415-A, FX-2200-BR.
# Competitor numbers look like L-9450, TS-BF200R, WG-FD4-SB, LF-500.
# People type them as CF-1100-XLS, cf1100xls or "CF 1100 XLS". All three forms are caught.
PART_NUMBER_RE = re.compile(
    r"\b[A-Za-z]{1,2}(?:-[A-Za-z0-9]{1,6}){1,3}\b"            # hyphenated: CF-1100-XLS, K-CF-1100-RK2, L-9450, TS-BF200R
    r"|\b[A-Za-z]{1,3}\d{3,4}[A-Za-z]{0,3}\d?\b"               # contiguous: cf1100xls, ND415A
    r"|\b[A-Za-z]{1,3} \d{3,4}(?: [A-Za-z]{1,3}\b)?"           # spaced:     FX 2200 BR, ND 415 A
)

_known_parts = None


def known_parts():
    """Normalized part numbers from data/catalog (Contoso and competitor). Cached."""
    global _known_parts
    if _known_parts is None:
        _known_parts = set()
        try:
            with open(os.path.join(DATA_DIR, "catalog", "parts.json"), encoding="utf-8") as f:
                _known_parts |= {normalize_part_number(p["id"]) for p in json.load(f)}
            with open(os.path.join(DATA_DIR, "catalog", "cross_reference.json"), encoding="utf-8") as f:
                _known_parts |= {normalize_part_number(x["competitorPartNumber"]) for x in json.load(f)}
        except FileNotFoundError:
            pass
    return _known_parts


def normalize_part_number(s):
    """CF-1100-XLS, cf1100xls, CF 1100 XLS  ->  cf1100xls"""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def extract_part_numbers(text, known=None):
    """Return {normalized: display} for part numbers mentioned in text.

    `known` is a set of normalized part numbers. When given, only matches that
    exist in the catalog are returned, which removes false positives such as
    'ASME A112' or 'in 2025 the'. In a real application the equivalent is a
    lookup against the product master, or a stricter regex for your own
    numbering scheme."""
    found = {}
    for m in PART_NUMBER_RE.finditer(text):
        raw = m.group(0).strip()
        norm = normalize_part_number(raw)
        if len(norm) < 5 or not any(ch.isdigit() for ch in norm):
            continue
        if known is not None and norm not in known:
            continue
        found[norm] = raw.upper()
    return found


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Markdown front matter
# ---------------------------------------------------------------------------

def parse_front_matter(text):
    """Return (metadata dict, body). Front matter is the '---' block at the top."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("["):
            try:
                v = json.loads(v)
            except ValueError:
                pass
        elif v.lower() in ("true", "false"):
            v = v.lower() == "true"
        elif v.isdigit():
            v = int(v)
        meta[k.strip()] = v
    return meta, text[end + 4:].lstrip("\n")


def print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))
