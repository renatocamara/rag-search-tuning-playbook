# Module 07: Going external (distributors, then the public)

Contoso's plan is the usual one: internal Customer Care first, distributor and rep partners next, and a public self-service assistant on the website after that. Each step widens the audience and narrows the tolerance for a wrong answer. A stale warranty term that a rep would catch becomes a commitment when a contractor reads it on the public site. This module is a checklist, not a demo; nothing here needs to run.

## What changes with the audience

| | Internal reps | Distributors and partners | Public |
|---|---|---|---|
| Who can ask | employees | authenticated partners | anyone |
| Content they may see | everything, including internal notes and pricing | their price list, their region's products, no internal notes | published content only |
| Consequence of a wrong answer | corrected by the rep | a wrong order, a claim | liability, reputation, safety on installation questions |
| Volume | hundreds a day | thousands | unbounded, plus abuse |
| Latency expectation | tolerant | moderate | strict |

## Checklist

### Content and retrieval (modules 01 to 06 as a gate)

- [ ] `stale@1` is 0 on the evaluation set, and the set contains trap questions for every known stale or duplicated source.
- [ ] Community and archived content is either excluded from the external index or filtered by default, with the relaxation logic (module 04) reviewed for the external case. For the public phase, exclude it.
- [ ] Every chunk has `status`, `doc_type`, `effective_date`, `brand`, and a new field for **audience** (`internal`, `partner`, `public`). Nothing without an audience tag is indexed.
- [ ] Pricing and availability come from the catalog (module 04), with the catalog returning the price list appropriate to the caller, never from document text.
- [ ] The evaluation set has been extended with external-style questions (installer questions, code compliance, "can I use X for Y") and with adversarial ones (prompt injection through the question, requests for competitor comparisons, requests for internal information).

### Entitlement and identity

- [ ] The front end authenticates the user (Entra ID for employees, Entra External ID or B2B for partners, anonymous for public) and passes an identity claim to `/query`.
- [ ] `/query` translates the identity into a search **security filter** that is always applied server-side: `audience/any(a: a eq 'public')` for anonymous users, `audience/any(a: a eq 'partner') and region eq '<their region>'` for partners, and so on. Azure AI Search does not enforce document-level security on its own; the application does, with a filter built from the token, never from a parameter the client can set.
- [ ] Separate indexes for internal and external content if the sets of sources differ a lot or if an accidental exposure would be severe. Separate indexes are the simpler control; a single index with an audience filter is the more flexible one. Either way the test is the same: an evaluation run with a public identity must never return a chunk tagged `internal`.
- [ ] Managed identities everywhere; no keys in the application, and the search service configured for Entra ID only.

### Gateway and safety

- [ ] API Management in front of `/query` with per-caller throttling, request size limits and quotas. Public traffic gets stricter limits.
- [ ] **Azure AI Content Safety** on both input and output: prompt injection detection (Prompt Shields) on the question, harmful content and groundedness detection on the answer. As an APIM policy or in the application.
- [ ] The grounding prompt for external users refuses out-of-scope requests (medical, legal, competitor comparisons, anything not about Contoso products) and never reveals internal document names, prices from internal sources or the prompt itself.
- [ ] Citations in every answer, with links the user can open. For public users, the link is the product page, not the internal document store.

### Operations

- [ ] Logging of question, retrieved `doc_id`s, answer and identity class (not the identity itself for public users) to Log Analytics, with retention agreed with legal.
- [ ] A dashboard for: volume, latency, `answer not found` rate, thumbs down rate, and the top questions with no good answer, reviewed weekly with Customer Care.
- [ ] The evaluation set runs on every deployment of ingestion or query code, and results are kept.
- [ ] The freshness design from module 05 is in place, with event-driven ingestion for bulletins and policy documents, because a public assistant cannot wait a week for a safety bulletin.
- [ ] Capacity: the public phase needs a search tier and replica count sized for the expected peak, and an Azure OpenAI deployment with provisioned throughput or a quota that covers it, tested with a load test before launch.
- [ ] A kill switch: a configuration flag that puts the public assistant into "search results only, no generated answer" mode within minutes if something goes wrong.

## Sequencing

The three phases share one index design and one `/query` implementation. What changes per phase is the audience filter, the gateway policy and the prompt. Build the audience field and the server-side filter in phase one, when the only audience is `internal`; adding `partner` and `public` later is then a tagging exercise on content, not an architecture change.

## References

* [Security filters for trimming results in Azure AI Search](https://learn.microsoft.com/azure/search/search-security-trimming-for-azure-search)
* [Azure AI Content Safety: Prompt Shields](https://learn.microsoft.com/azure/ai-services/content-safety/concepts/jailbreak-detection) and [groundedness detection](https://learn.microsoft.com/azure/ai-services/content-safety/concepts/groundedness)
* [API Management policies for Azure OpenAI](https://learn.microsoft.com/azure/api-management/azure-openai-enable-semantic-caching) (token limits, semantic caching, content safety)
* [Azure AI Landing Zones: security and governance guidance](https://azure.github.io/AI-Landing-Zones/)
