# Vertical Creation Guide

How to spin up a new Oracle vertical from scratch.

---

## Overview

An Oracle vertical is a standalone domain-expert AI consulting system: a curated knowledge base, a smart consultation engine, and a clean web surface. Each vertical lives in its own GitHub repo and is deployed independently.

This guide takes you from zero to a working vertical you can show to engineers in its domain.

---

## Prerequisites

- GitHub account with access to the Oracle platform repo
- Python 3.12+ and Node.js 20+
- Anthropic API key (Claude)
- OpenAI API key (embeddings)
- Brave Search API key (oracle-pipeline knowledge collection)
- A server to deploy on (any Linux VPS will do; 2 vCPU / 4GB RAM minimum for the cross-encoder + ChromaDB in-memory)

---

## Step 1: Create the GitHub Repository

Create a new repo: `svend206/<DomainName>Oracle`

Examples: `PumpOracle`, `ValveOracle`, `GasketOracle`, `NozzleOracle`

```bash
# Example for a pump vertical
gh repo create svend206/PumpOracle --private --description "Oracle vertical: hydraulic pumps & motors"
```

Clone it locally. Use `~/Projects/` as the permanent home for all Oracle repo clones — never use `/tmp/` (it's cleared on reboot):

```bash
git clone git@github.com:svend206/PumpOracle.git ~/Projects/pumporacle
```

---

## Step 2: Copy the Vertical Template

Copy everything from `vertical-template/` in the Oracle platform repo into your new vertical repo:

```bash
cp -r ~/Projects/oracle/vertical-template/. ~/Projects/pumporacle/
cd ~/Projects/pumporacle
```

The template includes:
- Full `ai/` directory structure (`00-identity` through `08-training-data`) — knowledge and curriculum layer
- Backend Python source (consultation engine, answer engine, database, etc.)
- Frontend React source (all pages and components)
- Dockerfile, docker-compose.yml, Caddyfile
- requirements.txt, .env.example
- deploy.sh, backup.sh

---

## Step 3: Replace Placeholders Throughout

Every file in the template uses `[VERTICAL_NAME]` and `[DOMAIN]` as placeholders. Replace them all:

```bash
# Dry run first to see what changes
grep -r "\[VERTICAL_NAME\]" . --include="*.py" --include="*.jsx" --include="*.md" --include="*.yml" --include="*.sh" --include="*.txt"

# Replace (macOS)
find . -not -path './.git/*' -type f | xargs sed -i '' 's/\[VERTICAL_NAME\]/PumpOracle/g'
find . -not -path './.git/*' -type f | xargs sed -i '' 's/\[DOMAIN\]/hydraulic pumps and motors/g'

# Replace domain references in Caddyfile, docker-compose, etc.
sed -i '' 's/\[DOMAIN_SLUG\]/pumporacle/g' Caddyfile docker-compose.yml
sed -i '' 's/\[DOMAIN_URL\]/pumporacle.com/g' Caddyfile docker-compose.yml
```

Key files to verify after replacement:
- `Caddyfile` — domain names must match your actual domain
- `docker-compose.yml` — container names and CORS_ORIGINS
- `backend/main.py` — service title, description
- `00-identity/SYSTEM-PROMPT.md` — all domain references
- `01-curriculum/ROADMAP.md` — all phase names and topics
- `07-development-log/LOG.md` — entry 001 context

---

## Step 4: Write the System Prompt

Open `00-identity/SYSTEM-PROMPT.md` and write your domain's system prompt.

This is the most important document. It defines:
- **Identity** — what this vertical is an expert in
- **Core principles** — how it reasons (first principles, honesty, show your work)
- **Current knowledge level** — what it knows well vs. is still learning
- **Core engineering reference** — key equations, tables, rules of thumb for the domain
- **Operating modes** — learning, problem-solving, design review, innovation
- **Scope** — what's in and out of scope

Look at the FilterOracle system prompt (`~/Projects/filteroracle/ai/00-identity/SYSTEM-PROMPT.md`) for a complete example. The structure is proven — adapt the content for your domain.

**Tip:** The "Core Engineering Reference" section is the most valuable part. It's the quantitative backbone that the AI uses to sanity-check retrievals and do first-pass calculations. Take time to build it well before you start collecting knowledge.

---

## Step 5: Write the Curriculum Roadmap

Open `01-curriculum/ROADMAP.md` and define the learning phases for your domain.

Structure: 8-10 phases that go from fundamentals to advanced/specialty topics. For each phase, define:
- What topics are covered
- What the AI should be able to do after this phase
- What sources to prioritize

Example phases for PumpOracle:
1. Fluid power fundamentals (pressure, flow, power)
2. Pump types and operating principles (gear, vane, piston, screw)
3. Performance characteristics (flow vs. pressure curves, efficiency maps)
4. Sizing and selection methodology
5. System integration (circuit design, pressure setting, flow control)
6. Fluid compatibility (mineral oil, synthetics, fire-resistant)
7. Condition monitoring and failure analysis
8. Standards and specifications (ISO 4413, SAE J2413, OEM specs)
9. Advanced topics (variable displacement, servo pumps, pressure compensators)

Create the corresponding phase directories under `01-curriculum/`:
```bash
mkdir -p 01-curriculum/phase-01-fluid-power-fundamentals
# etc.
```

---

## Step 6: Domain Exploration & Knowledge Distillation

This is the step most people skip — and the reason some verticals are good and others are mediocre.

Before running the oracle-pipeline or ingesting any documents, **explore the domain deeply with Claude.** The goal is to let Claude accumulate vertical-specific understanding through conversation, then capture that understanding as structured curated reference documents.

### Why this matters

The oracle-pipeline is good at finding and ingesting source material. But source documents are often incomplete, locked behind paywalls, dense with context you have to already know, or simply unavailable. During exploration, Claude synthesizes across its training knowledge, your questions, and any documents you share — and can produce structured reference material that fills gaps no single document could fill.

The curated reference `.md` files produced by this step are the highest-value layer in the knowledge base. They:
- Are already structured for retrieval (headers, tables, formulas, worked examples)
- Fill gaps that source documents leave open
- Represent validated knowledge — synthesized and reviewed, not raw text
- Are portable — they travel with the repo, not a vector store

### The workflow

**1. Exploration sessions** — Work through the domain with Claude. Cover:
- Core physics and first principles ("explain Darcy's law as it applies to filter pressure drop")
- Selection methodology ("walk me through how a filter engineer sizes a filter for a hydraulic circuit")
- Failure modes ("what are the most common filter failure modes and how do you diagnose them?")
- Standards landscape ("what are the key standards governing filter performance testing?")
- Vendor landscape ("who are the major filter manufacturers and what are their positioning differences?")
- Edge cases ("what happens when fluid viscosity is highly temperature-dependent?")

**2. Identify gaps** — As you explore, note topics where:
- Claude flags uncertainty or low confidence
- Source documents are thin or unavailable
- The curriculum roadmap has phases not yet covered

**3. Synthesize curated references** — At the end of each exploration session, ask Claude to produce structured reference documents covering what was learned. Examples from SprayOracle:
- `REFERENCE-Key-SMD-Correlations-Atomization.md`
- `REFERENCE-Nozzle-Materials-Wear-Guide.md`
- `REFERENCE-Spray-Troubleshooting-Decision-Trees.md`
- `REFERENCE-Non-Newtonian-Fluid-Atomization.md`

Place these in `ai/02-knowledge-base/curated-references/`. They will be ingested alongside source documents in Step 9.

**4. Refine the system prompt** — The exploration will reveal what reference data belongs in the system prompt itself (equations, tables, rules of thumb that should always be in context). Go back and update `00-identity/SYSTEM-PROMPT.md` with what you learned.

### What good curated references look like

Each file should be self-contained and specific:

```markdown
# Filter Element Collapse Pressure — Reference

## What It Is
Collapse pressure is the differential pressure at which a filter element 
structurally fails...

## Standard Test Method (ISO 2941)
...

## Typical Values by Media Type
| Media | Typical Collapse Pressure |
|-------|--------------------------|
| ...   | ...                      |

## Selection Rules of Thumb
1. Never select a filter whose collapse pressure is less than 2× the system relief valve setting
2. ...

## Common Failure Patterns
...
```

**Don't move to Step 7 until you have at least 8-10 curated reference files covering the core topics of your domain.** This is not optional — it's what makes the difference between a vertical that gives vague answers and one that gives specific, confident, cited recommendations.

---

## Step 7: Configure oracle-pipeline

In the Oracle platform repo (`oracle-pipeline/`), create a config for your vertical:

```bash
mkdir -p oracle-pipeline/verticals/hydraulic-pumps
```

Create `oracle-pipeline/verticals/hydraulic-pumps/config.yaml`:

```yaml
vertical_name: hydraulic-pumps
display_name: Hydraulic Pumps & Motors
description: Knowledge collection for hydraulic pump and motor selection and application

phases:
  phase_01_standards:
    name: Standards and Specifications
    topics:
      - ISO 4413 hydraulic fluid power safety
      - SAE J2413 fluid power circuit diagrams
      - ISO 4391 pump displacement measurement
    sources:
      - type: brave_search
        queries:
          - "ISO 4413 hydraulic safety standard site:iso.org"
          - "hydraulic pump efficiency measurement standard"
          # Add more targeted queries here

  phase_02_manufacturer_docs:
    name: Manufacturer Application Guides
    topics:
      - Pump selection methodology
      - Performance curves and ratings
      - Installation and commissioning
    sources:
      - type: brave_search
        queries:
          - "hydraulic piston pump selection guide filetype:pdf"
          - "gear pump application engineering"
          # etc.

domain_vocabulary:
  - displacement (cc/rev)
  - volumetric efficiency
  - overall efficiency
  - pressure compensator
  - variable displacement
  - case drain
  - cavitation
  - prime mover
  # etc.
```

---

## Step 8: Run Knowledge Collection

```bash
cd oracle-pipeline

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, BRAVE_API_KEY, OPENAI_API_KEY

# Run Phase 1: Standards
python -m pipeline run --vertical hydraulic-pumps --phase phase_01_standards

# Check what was collected
python -m pipeline status --vertical hydraulic-pumps

# Run Phase 2: Manufacturer docs
python -m pipeline run --vertical hydraulic-pumps --phase phase_02_manufacturer_docs

# Continue phase by phase...
```

**Tip:** Run phases incrementally and review the synthesized chunks after each one. The pipeline logs gaps and low-confidence content. Review `gap-tracker.jsonl` after each phase to plan the next collection round.

**Tip:** Don't rush collection. 500 high-quality, well-synthesized chunks beats 5000 scraped paragraphs. Quality over quantity in the knowledge base.

---

## Step 9: Ingest into ChromaDB

Once you have good synthesized content from the pipeline, ingest it into the vertical's ChromaDB:

```bash
cd ~/Projects/pumporacle

# Set up environment
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, OPENAI_API_KEY, CHROMA_PATH

# Ingest chunks from the pipeline
python ai/02-knowledge-base/batch_ingest.py --source /path/to/oracle-pipeline/verticals/hydraulic-pumps/

# Verify the knowledge base
python ai/02-knowledge-base/test_setup.py
python ai/02-knowledge-base/query.py "what type of pump for high pressure low flow applications?"
```

Check coverage with `test_coverage.py` — it identifies topic areas with weak retrieval so you know where to do more collection.

---

## Step 10: Deploy

```bash
# 1. Configure production environment
cp .env.example .env.production
# Edit .env.production with production values (API keys, domain, admin key, etc.)

# 2. Update Caddyfile with your domain
# (already done in Step 3)

# 3. Build and start
docker compose build
docker compose up -d

# 4. Verify health
curl http://localhost:8000/api/health

# 5. Test the consultation surface
# Open https://pumporacle.com in browser
# Try an /ask question — verify RAG retrieval is working
# Try a /consult session — verify the two-phase flow works
```

**Domain + DNS:** Point your domain to the server IP. Enable Cloudflare proxy. Set up "Full (Strict)" SSL mode. Generate Cloudflare origin certificates and place them in `certs/`.

**Backups:** Set up the daily backup cron:
```bash
chmod +x backup.sh
crontab -e
# Add: 0 3 * * * /opt/pumporacle/backup.sh >> /opt/pumporacle/backups/backup.log 2>&1
```

---

## Checklist

Before launching, verify:

- [ ] All `[VERTICAL_NAME]` placeholders replaced
- [ ] System prompt written and reviewed
- [ ] Curriculum roadmap written
- [ ] At least Phase 1 and Phase 2 knowledge collected and ingested
- [ ] `test_setup.py` passes
- [ ] At least 5 test queries return relevant results in `query.py`
- [ ] Backend starts without errors
- [ ] Frontend builds and loads
- [ ] `/ask` surface returns coherent answers
- [ ] `/consult` surface completes a full gathering → answering flow
- [ ] SSL working
- [ ] Backup cron configured
- [ ] `.env` and `.env.production` NOT committed to git
- [ ] `07-development-log/LOG.md` Entry 001 written with launch context

---

## What Makes a Good Vertical

- **Specific domain** — "hydraulic pumps" not "hydraulics generally". The narrower the scope, the deeper the expertise can go.
- **Engineering depth** — The system prompt should have real equations and tables, not just descriptions.
- **First principles** — The AI should be able to derive answers, not just retrieve them.
- **Honest uncertainty** — The confidence levels and gap tracking should be used. Better to say "I don't know" than to hallucinate.
- **Outcome tracking** — Enable the CPVP follow-up system from day one. Don't skip outcome tracking.

---

## Getting Help

Read `ARCHITECTURE.md` in the Oracle platform repo for the full technical picture. Read `oracle-pipeline/SESSION_HANDOFF.md` for the current pipeline state. Log architectural questions in `decision_log/`.
