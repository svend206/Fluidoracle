# Fluidoracle

Vendor-neutral AI consulting platform for industrial fluid system components.

## Architecture

One codebase, two deployment platforms:

- **FPS (Fluid Power Systems)** — Closed-loop hydraulic/pneumatic circuits. Verticals: hydraulic filtration, pumps, valves, seals.
- **FDS (Fluid Delivery Systems)** — Open-loop fluid delivery processes. Verticals: spray nozzles, atomizers, precision applicators.

## Structure

```
core/               Shared methodology — consultation engine, retrieval, auth, database
platforms/fps/      Fluid Power Systems platform config and verticals
platforms/fds/      Fluid Delivery Systems platform config and verticals
frontend/           React + Vite + Tailwind SPA
vector-store/       Per-vertical ChromaDB + BM25 indexes
tests/              Test fixtures and integration tests
deploy/             Per-platform Docker/Caddy deployment configs
docs/               Platform documentation (CPVP, business model, compute strategy)
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt
cd frontend && npm install

# Run backend
uvicorn main:app --reload

# Run frontend dev server
cd frontend && npm run dev

# Ingest a knowledge base
python -m core.retrieval.ingest --platform fps --vertical hydraulic_filtration

# Run tests
python -m tests.run_tests --vertical hydraulic_filtration
```

## Key Documentation

- **[Compute Strategy](docs/compute-strategy.md)** — LLM vs. deterministic code decision matrix. **Read this before writing any new feature.** Defines when to use LLM calls vs. Python/SQL, confidence scoring, pre-computation injection patterns, and cost monitoring.
- **[CPVP](docs/cpvp.md)** — Component Performance Verification Protocol
- **[Business Model](docs/business-model.md)** — Platform revenue and growth model
- **[Fluid Database Design](docs/fluid-database-design.md)** — oracle.db schema and fluid property lookups

## Static Site

The marketing site (fluidoracle.com) is served from the `gh-pages` branch. Do not modify gh-pages content from this branch.
