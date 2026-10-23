# Kestrel Supply: an agentic B2B commerce prototype

A buying agent for a (fictional) ERP-integrated B2B distributor. It knows each customer's contract price and credit position, follows the business rules, proposes carts and quote requests for the buyer to confirm, and hands off to a sales rep when a human should decide. A seller desk covers the other side of the journey.

> **Live demo:** _add your Render URL here_
> Pages: **Assistant** (with a live decision trace) · **Seller desk** · **How it works** (architecture, agent graph, decision layers, fallback ladder) · **Evals** (metrics + experiment log) · **Design system** (tokens as the source of truth)

**Core principle:** the LLM decides *what to do*; deterministic code decides *what is true and what is allowed*. Prices, stock, credit rules and every write action live in code. The model can only propose writes, and the buyer confirms them.

## What it demonstrates

| Area | What's built |
|---|---|
| **Agent design** | LangGraph state machine: router LLM → intent-scoped tools (least privilege) → tool-calling agent → deterministic output guard with one self-correction retry |
| **B2B journeys** | Account-specific pricing (contract, price group, volume tiers), stock per warehouse, reorders from history, carts, quote requests (credit limit, prepayment, €10k threshold, discount requests), handoff to sales, seller approval |
| **Fallbacks** | Model fallback (Haiku → Sonnet), ERP outage signal, router failure → read-only mode, unverified-price guard, recursion limit, rate limits. Two are demo switches in the UI |
| **Retrieval** | Hybrid search (dense + BM25) with RRF and cross-encoder reranking over the catalog and policy PDFs; manifest-controlled freshness, so a retired policy can never be cited |
| **Evaluation** | 49 agent cases (incl. multi-turn, injection, off-topic, unanswerable, simulated outages) graded by an LLM judge *and* deterministic checks; retrieval per search stage; ablation variants; quality gates for CI; an experiment log in the UI |
| **Design system** | `design-tokens.json` (values + usage rules) → generated CSS for light and dark → published for AI tools; agent output renders through token-based components, never LLM-written markup |

## Architecture

```
Experience   Angular: Assistant · Seller desk · Evals · Design system      (tokens.json → tokens.css)
API          FastAPI: validation, rate limits, account scoping, confirm endpoints (the only write path)
Agent        LangGraph: route → decline | agent ⇄ tools → verify (retry once) → end
Tools        read: search_catalog, get_price_and_stock, get_order_history, search_policies
             propose: propose_cart, request_quote, handoff_to_sales  (never write)
Data         mock ERP (accounts, pricing, stock, credit, orders) · Qdrant: catalog + policies (dense + BM25)
Offline      ingestion (PDF manifest, hashing, idempotent upserts) · eval harness (judge + checks + gates)
```

## Run locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, an Anthropic API key.

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env      # never committed

uv sync
uv run python -m rag.ingest --recreate          # index policies + catalog
uv run rag-server                                # API on :8000

cd frontend && npm ci && npm start               # UI on :4200 (proxies /api to :8000)
```

Single-process mode: `cd frontend && npm run build`, then `RELOAD=false uv run rag-server`. FastAPI then serves the UI on :8000.

## Evaluate

```bash
uv run python -m rag.evals.run                          # full suite, production config (~2 min)
uv run python -m rag.evals.run --variant no_router      # ablations: no_router, no_price_guard, no_model_fallback
uv run python -m rag.evals.run --skip-agent             # retrieval only, no LLM cost
```

Reports are written to `evals/results/`; the Evals page shows the latest run and the experiment log (`evals/experiments.json`). A failing quality gate exits with code 1.

## Deploy to Render

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, then pick the repo (`render.yaml`).
3. Set `ANTHROPIC_API_KEY` in the dashboard.

The Docker image builds the UI, generates the design tokens, indexes the catalog and policies, and downloads the models at build time. The service needs about 0.5 GB of RAM, so use an instance with more than 512 MB.

## Project layout

```
src/rag/
  agent.py          LangGraph agent: router, scoped tools, guard, fallbacks
  tools.py          the agent's tools (read + propose), all traced
  erp.py            mock ERP: pricing rules, stock, credit, carts, sales queue
  guards.py         deterministic price and citation checks
  catalog.py        product indexing and search
  retrieval.py      policy search with freshness filters
  search.py         shared hybrid search + rerank pipeline
  ingest.py         policy PDF ingestion (manifest, hashing, idempotent)
  api.py            FastAPI endpoints
  evals/            dataset, judge, agent and retrieval evals, quality gates
resources/          commerce data (products, accounts), policy PDFs + manifest
evals/              eval cases, catalog queries, results, experiment log
frontend/           Angular app + design-tokens.json + token build script
scripts/            reproducible generator for the policy PDFs
```

## Simplified in this prototype

The ERP is a JSON-backed mock with real pricing rules (in production: SAP or Dynamics behind the same tool interface). Memory, carts and the sales queue are in-memory on a single instance. There's no authentication; the account switcher stands in for SSO, while account scoping is enforced server-side. All company data is fictional.
