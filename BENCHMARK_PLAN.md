# LLM Operations Benchmark — Plan

Goal: define specific operations **for each agent**, based on that agent's
own query-building and RAG (retrieval-augmented generation) mechanics, then
test them for real against the live `/chat` APIs and score accuracy using an
independent third-party LLM as judge.

## Why agent-specific, not one shared list

Earlier versions of this benchmark used one shared list of behaviors tested
identically across all four agents (plan-gating, human-gated language, etc.).
This version is different by design: **each agent gets its own operations**,
built from that specific agent's own tools, parameters, and knowledge base —
because query building and retrieval genuinely work differently per agent
(different category filters, different entity types to resolve, different
knowledge bases). Forcing one shared template across agents with different
tool signatures (e.g. IT Ops's `search_knowledge_base` has no category
parameter, unlike the other three) would test something that isn't real for
that agent.

## The two capabilities every agent's operations are built around

1. **Query building** — turning a natural-language message into a correct
   tool call: the right search terms, the right category/filter, the right
   specific entity (a lead, a segment, a service, a location) resolved from
   a partial or informal reference, and any specific sub-parameter (a
   runbook id chained from a search result, a specific month, a process
   type) extracted correctly.
2. **RAG capabilities** — using what was actually retrieved correctly: the
   final answer stays grounded in retrieved content (no invented figures,
   names, or steps), and when nothing relevant is found, the agent says so
   rather than force-fitting a weak match or guessing.

## Operation shape — 4 per agent

Every agent gets the same 4-operation *shape*, populated with that agent's
own real tools, parameters, and data:

| # | Operation | Query building or RAG? |
|---|-----------|------------------------|
| 1 | **Search query formulation** (+ category filter selection, where the agent's search tool has one) | Query building |
| 2 | **Entity/parameter extraction for structured calls** | Query building |
| 3 | **Grounded generation from retrieval** | RAG |
| 4 | **No-match / low-relevance handling** | RAG |

**4 agents × 4 operations × 2 cases = 32 cases total.**

## What's tested per agent (grounded in each agent's real tools/data)

**IT Ops** — `search_knowledge_base(query)` has no category filter, so
operation 1 tests query specificity only. Operation 2 tests picking the
right ticket `category` (from real categories like Email, Network, Print)
and the right `service` key (vpn, email, software_center, intranet,
identity) for a status check.

**HR** — `search_hr_policy(query, category)` has a real category filter
(Leave, Benefits, Conduct, Compensation, General). Operation 2 tests
resolving the right `process` key (e.g. `onboarding`) plus correct
subject/date/employment-type, and passing a real location to
`get_location_guidelines`.

**Sales** — `search_playbook(query, category)` has a real category filter
(ICP, Pricing, Competitive, etc.). Operation 2 tests fuzzy-resolving a
partial lead name (e.g. "Helio" → Helio Freight) and picking the correct
`sequence` type matching the actual situation (trial-activation vs
inbound-demo vs nurture).

**Data Analysis** — `search_analytics_kb(query, category)` has a real
category filter (Methodology, Reporting, Limitations, etc.). Operation 2
tests fuzzy-resolving a segment name and correctly parsing a specific
period (e.g. "back in July" → `2026-07`) rather than always defaulting to
the latest month.

## Grading

Every case is graded by the independent judge LLM against a written rubric
(`judge.rubric_score()`). The judge must never be one of the agents' own
underlying models — see `models.json`.

## Running it

    curl -X POST localhost:8101/demo/reset
    curl -X POST localhost:8102/demo/reset
    curl -X POST localhost:8103/demo/reset
    curl -X POST localhost:8104/demo/reset
    python run_benchmark.py

All four agents (ports 8101–8104) must already be running.

## Open question

Which LLM should be the judge? It must be independent of whatever
`AZURE_OPENAI_DEPLOYMENT_NAME` the four agents are actually running on — see
`models.example.json`.
