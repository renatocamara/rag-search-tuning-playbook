# Module 03: Chunking spec sheets (tables need their headings)

**Symptom at Contoso:** "What is the rough-in for the CF-1100-XLS?" returns a passage that contains `| Rough-in ... | 11.5 in |` but not the product name, or a passage from the wrong product's table. The assistant either answers "I could not find that" or answers from a neighbouring product. Prices, warranty periods and kit numbers fail the same way.

**Root cause:** fixed-size chunking. A spec sheet is a page of prose followed by a table. Cut into 400-character windows, the table rows end up in a chunk with no heading, no product name and no part number. The chunk's embedding is generic ("some attributes and values"), and its text has nothing for the keyword leg to match. Everything that makes the passage identifiable is in the previous chunk.

**Fix:** chunk on structure, never split a table, and prepend a contextual header (document title, part numbers, section) to every chunk.

Time: 10 minutes. This module re-indexes the documents twice; each run takes a minute or two.

## Step 1: Index the naive way and watch it fail

```bash
python scripts/setup/04_ingest.py --chunking naive --force
python scripts/demo/query.py "What is the rough-in for the CF-1100-XLS?" --mode semantic --current
python scripts/demo/query.py "What is the list price of the CF-1100-XL?" --mode semantic --current --answer
python scripts/demo/query.py "How many gallons per hour does the FX-2200-BR chiller deliver?" --mode semantic --current
```

Look at the passages. The chunks that contain the answer start mid-sentence or mid-table and carry no product name (the `parts:` line is empty or shows a different part). Hybrid and semantic ranking cannot rescue a chunk that has nothing identifying in it.

Print the chunks of one document to see the cuts:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, "scripts"); import common
r = common.search_query({"search": "*", "filter": "doc_id eq 'spec-CF-1100-XLS'", "orderby": "chunk_index", "select": "chunk_index,part_numbers,content", "top": 20})
for c in r["value"]:
    print(f"--- chunk {c['chunk_index']}  parts={c['part_numbers']}\n{c['content'][:300]}\n")
EOF
```

Run the evaluation set for a baseline:

```bash
python scripts/eval/run_eval.py --mode semantic --current --label naive-chunking
```

The `spec_value` category is where it hurts.

## Step 2: Index on structure

```bash
python scripts/setup/04_ingest.py --chunking structured --force
```

`scripts/chunking.py` does three things:

1. Splits on Markdown headings (`#`, `##`, `###`), so a section is the unit.
2. Treats a Markdown table as indivisible. Long sections without tables are split by paragraph up to 1,200 characters.
3. Prepends a header to every chunk:

    ```
    Document: Specification sheet CF-1100-XLS
    Part numbers: CF-1100-XLS, K-CF-1100-RK2, S-CF-IR3, B-CF-4AA
    Section: Specifications
    ```

The header is the piece most pipelines miss. It costs about 100 characters per chunk and gives every chunk a product identity for both the embedding (the vector now sits near "CF-1100-XLS specifications", not near "generic table") and the keyword leg (the part number is literally in the text and in the `part_numbers` field).

Repeat the three questions and the evaluation:

```bash
python scripts/demo/query.py "What is the rough-in for the CF-1100-XLS?" --mode semantic --current
python scripts/eval/run_eval.py --mode semantic --current --label structured-chunking
python scripts/eval/run_eval.py --compare results/<naive>.json results/<structured>.json
```

## Step 3: Look at the other documents

The same strategy handles the other document types without special cases:

* Install guides: one chunk per numbered section ("Before you start", "Servicing"), the troubleshooting table intact.
* Warranty policy: the coverage table is one chunk, the claim procedure another.
* Cross reference guide: the whole table is one chunk, so "Litware L-9450" and "CF-1100-XL" are in the same passage.
* Forum threads: short, one chunk.

Check with `--dry-run`, which prints chunk counts per document without touching the index:

```bash
python scripts/setup/04_ingest.py --chunking structured --dry-run
python scripts/setup/04_ingest.py --chunking naive --dry-run
```

## Real spec sheets are PDFs

The playbook uses Markdown so the structure is visible. Real spec sheets are PDFs, often two columns with a table across the bottom, and the extraction step decides whether a table survives at all:

| Extraction | Result on a spec sheet table |
|---|---|
| Plain text extraction (`pypdf`, most crawlers) | Rows interleaved with column text; the table is unrecoverable, and no chunker can fix it |
| Azure AI Document Intelligence, `prebuilt-layout` with Markdown output | Headings as `#`, tables as Markdown tables, in reading order. Feeds the structured chunker directly |
| Vision model on a page image | Works, expensive, best reserved for pages layout fails on |

If your PDFs were extracted as plain text, the highest-value change is usually re-extracting with the layout model, not changing the chunker.

Two more things that matter for tables: keep the header row with every table chunk if you ever do have to split a long table, and consider emitting a second, sentence-form chunk per row for wide tables ("CF-1100-XLS: rough-in 11.5 in, flow rate 1.28 gpf, repair kit K-CF-1100-RK2"). The sentence form embeds far better than pipe-delimited text.

## What to change in your application

| Setting | Before | After |
|---|---|---|
| Chunker | fixed size (tokens or characters) | structure-aware: headings, tables whole, size cap per section |
| Chunk text | raw window | contextual header + window |
| PDF extraction | plain text | layout model with Markdown output |
| `part_numbers` per chunk | not set or document-level only | extracted from the chunk text, including the header |

## References

* [Chunk large documents for vector search](https://learn.microsoft.com/azure/search/vector-search-how-to-chunk-documents)
* [Document Intelligence layout model with Markdown output](https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/layout)
* [Text Split skill](https://learn.microsoft.com/azure/search/cognitive-search-skill-textsplit) (the indexer-side equivalent; it does not keep tables whole, which is one reason this playbook chunks in the application)
