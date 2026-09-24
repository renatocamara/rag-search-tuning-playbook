# Setup 5: Exposing the tuned retrieval to users

Everything in the modules happens at the index and the query. Once the query is right, there are three common ways to put it in front of Customer Care reps. The retrieval choices are the same in all three; what differs is who builds the request.

## Option A: your own API (recommended when you already have one)

The application owns the request body. `scripts/demo/retrieval.py` is a reference implementation: `build_query()` returns the exact JSON to post to `/indexes/{index}/docs/search`, and `answer()` shows the grounding prompt. Copy both into your `/query` handler. The order of operations from module 04 (detect part numbers, look them up in Cosmos DB, search with a filter, answer with citations) fits in about 60 lines.

Front ends such as Copilot Studio, Teams or a web app call the API through API Management, which is where authentication, throttling and the Content Safety policy live (module 07).

## Option B: an Azure AI Foundry agent with the Azure AI Search tool

If the assistant is a Foundry agent, the search tool builds the request for you, but exposes the same knobs:

1. In the Foundry project, add a **connection** to the search service (Entra ID authentication, project managed identity with *Search Index Data Reader* on the service).
2. In the agent, add the **Azure AI Search** tool, choose the connection and the index `contoso-kb`.
3. Set **Query type** to `vector_semantic_hybrid` (this is hybrid + semantic ranker, the "after" state of module 01). `vector` alone is the "before" state; if an existing agent is configured that way, this single dropdown is the fix.
4. Set **Top k** to 5 to 10.
5. Add a **filter** (`status eq 'current'`) where the tool supports one; if your version of the tool does not, either keep archived content out of the index the agent uses, or move the filtering to Option A.
6. In the agent **instructions**, tell it to always use the search tool for product questions, to quote part numbers exactly, and to say when the answer is not in the results.

The semantic configuration used is the index default (`contoso-semantic`). Scoring profiles are not applied by agent tools that use agentic retrieval; filters and index design carry the weight there.

For the structured lookup of module 04, add a second tool: an **OpenAPI** tool in front of a small function that queries Cosmos DB by part number, or an **Azure Functions** tool. The agent then has one tool for facts and one for explanations, and the instructions say which to call first.

## Option C: a knowledge base (agentic retrieval) over the index

Azure AI Search knowledge sources and knowledge bases wrap the same index with query planning: the service rewrites the user question into several sub-queries, runs them in parallel and merges the results, then optionally synthesizes an answer. It is a good fit for multi-part questions ("what replaces the CF-1101-XL and what kit does the replacement use"). It uses the index as built here, so the analyzer, metadata and chunking still matter. Two things to know: the knowledge base's chat model has to be deployed in a Foundry account reachable from the search service (in a private network, through a shared private link), and scoring profiles do not apply.

## Which one for Contoso

Contoso's assistant already runs as an API behind API Management with a Copilot Studio front end, so Option A is the minimal change: adjust the request body, add the Cosmos DB lookup, add the filter, re-run the evaluation set. Options B and C are the paths if the assistant is rebuilt on Foundry agents later; the index work is reused as is.
