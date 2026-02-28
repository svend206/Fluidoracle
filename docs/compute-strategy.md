# Fluidoracle: Compute Strategy Addendum

## LLM vs. Deterministic Code Decision Matrix

Principle: LLMs are expensive per-call and good at judgment, synthesis, and natural language. Deterministic code is free per-call and good at computation, lookup, and routing. Every decision point in the platform should use the cheapest reliable method. When an LLM call is required, pre-compute everything possible and inject it as context so the LLM spends tokens on judgment, not arithmetic.

-----

## Decision Matrix

### ALWAYS USE LLM (This Is The Product)

| Function | Why LLM Is Required | Cost Management |
|---|---|---|
| **Gathering conversation** | Engineer describes problems in natural language. Claude must demonstrate domain expertise through diagnostic questioning, adapt to incomplete/ambiguous inputs, recognize when symptoms point to a different root cause than the engineer assumes. This is judgment and natural language — irreplaceable. | Front-load structured intake (see below). Set question budget in prompt: "transition to answering within 4-6 exchanges." Use operating context portability to skip re-gathering shared parameters on second-vertical consultations. |
| **Answering synthesis** | Claude must synthesize multiple retrieved catalog chunks into a coherent recommendation with reasoning chains, tradeoff analysis, and cited sources. Must weigh competing factors (cost vs. performance vs. availability) using engineering judgment. | Pre-compute everything computable (fluid properties, ΔP estimates, cleanliness code interpretations) and inject as context. Claude reasons with pre-computed numbers, doesn't derive them. |
| **Commissioning follow-up conversations** | CPVP staged check-ins (30/90/180 day) are conversational — Claude interprets the engineer's natural language performance reports, compares against expected outcomes, identifies potential issues. | Keep these brief. Structure the check-in prompts to elicit specific data points. Pre-compute expected performance baselines from the original recommendation. |
| **Prompt adaptation for SprayOracle nozzle content** | Reworking standalone SprayOracle prompts into platform template format requires judgment about what to preserve vs. restructure. | One-time cost during Sprint 3. Not a runtime cost. |

### NEVER USE LLM (Deterministic Code Is Better AND Cheaper)

| Function | What To Use Instead | Implementation Notes |
|---|---|---|
| **Fluid property lookups** | `core/reference/oracle.db` + Python functions | Viscosity-temperature curves, specific gravity, compatibility data. The oracle.db from the Oracle repo seeds this. When consultation captures "VG46 at 80°C," look up kinematic viscosity, don't ask Claude. Expand the database over time. |
| **ISO 4406 code interpretation** | Lookup table in reference_data.py or SQLite | "16/14/11" → particle counts per mL at 4μm/6μm/14μm. Pure table lookup. Inject the interpretation into LLM context: "Target cleanliness 16/14/11 corresponds to 320-640 particles ≥4μm per mL." |
| **Beta ratio calculations** | Python function | β₁₀₀₀[x] = 1000 means 99.9% efficiency at x microns. Formula, not judgment. Compute and inject. |
| **ΔP estimation** | Python function using fluid properties + flow rate + element specs | Theoretical pressure drop across filter elements. Uses viscosity (from oracle.db), flow rate (from gathered params), element specifications (from KB metadata). Pre-compute, inject as context: "Estimated clean ΔP: 1.3 bar at 120 LPM." |
| **Retrieval** (semantic search, BM25, reranking) | Existing pipeline: embeddings + BM25 + cross-encoder | Already correctly implemented as deterministic/small-model inference. No changes needed. |
| **Confidence scoring** | Computed from retrieval metrics | See dedicated section below. |
| **Follow-up scheduling** | Database trigger / cron | 30/90/180 day schedule. Pure date arithmetic. |
| **Operating context persistence** | JSON in SQLite | Store, retrieve, transfer between verticals. Pure data operations. |
| **Parameter validation** | Python type checking / range validation | "Flow rate must be positive." "Pressure must be in range 0-700 bar." No LLM needed. |
| **Demand signal logging** | Database insert | Log off-vertical queries, timestamps, source vertical. Pure writes. |
| **Auth, email, session management** | Existing code | Already deterministic. No changes. |
| **Ingestion pipeline** | Existing chunking + embedding | Already deterministic. No changes. |

### REPLACE LLM WITH DETERMINISTIC CODE (Currently Using LLM, Shouldn't Be)

| Function | Current State | Target State | Savings |
|---|---|---|---|
| **Session title generation** | Full Claude API call: "Summarize this hydraulic filter consultation in 5 words" | Extract the application_domain from gathered_parameters (already structured). Use a template: "{domain} — {primary_concern}". Example: "Return Line Filtration — Contamination Control". If you want it prettier, use the first substantive noun phrase from the engineer's opening message (regex or spaCy, not Claude). | ~1 API call per consultation eliminated |
| **Warmup queries** | Sends a query to Claude on startup | Warmup should exercise the retrieval pipeline (embed a test query, hit ChromaDB, load BM25 index), not call the LLM. The point is to load models into memory, not generate text. | Eliminates startup LLM call entirely |

### USE EMBEDDINGS, NOT FULL LLM (Cheap Intelligence)

| Function | Approach | Why Not Full LLM |
|---|---|---|
| **Vertical routing** (future: first-message classification) | Cosine similarity between message embedding and each vertical's description embedding. You're already running the embedding model for retrieval — this is a marginal cost of one additional embedding per message. Route to the vertical with highest similarity above threshold. Fall back to explicit selection if ambiguous. | A full Claude call to classify "I have a contamination problem in my hydraulic return line" as filtration is wildly expensive for a task that embedding similarity solves at >95% accuracy. |
| **Off-vertical query detection** (demand signal capture) | Same technique — compute similarity of each user message against current vertical's domain description vs. other verticals'. If similarity to current vertical drops below threshold while another rises, log it as off-vertical demand. | This runs in parallel with the conversation. The LLM already handles obvious off-vertical questions through its prompt instructions. The embedding-based detection catches the subtler signals for analytics without adding API cost. |
| **Query expansion for retrieval** (future optimization) | If engineers' natural language doesn't match catalog terminology, use an embedding-based synonym map or a small curated thesaurus. "Clogged filter" → also search "high differential pressure", "restricted flow". | A Claude call for query expansion adds latency and cost to every retrieval. A synonym dictionary or nearest-neighbor embedding lookup is instant and free. Only escalate to LLM-based expansion if the cheap methods fail to return adequate results. |
| **Cross-vertical relevance scoring** (future) | When the platform has 4+ verticals, score incoming queries against all vertical embeddings to pre-rank which verticals might be relevant. | Batch embedding comparison is orders of magnitude cheaper than asking Claude to classify against multiple categories. |

-----

## Confidence Scoring: Replace LLM Self-Assessment With Computed Metrics

The current answer engine returns a confidence level. If this is Claude self-reporting confidence, replace it with computed retrieval metrics. LLMs are notoriously poor at calibrating their own uncertainty.

### Signals to compute (all available from the retrieval pipeline):

```python
def compute_confidence(retrieval_result) -> dict:
    """Compute confidence from retrieval metrics, not LLM self-assessment."""
    signals = {
        # How many chunks scored above the relevance threshold?
        "chunks_above_threshold": count(r for r in results if r.score > THRESHOLD),

        # What's the score gap between top result and the rest?
        "top_score_margin": results[0].score - results[1].score if len(results) > 1 else 0,

        # Do top results converge on same product family / manufacturer?
        "source_convergence": len(unique_sources(results[:5])) / 5,
        # 1.0 = all different sources (low convergence, lower confidence)
        # 0.2 = all from same source (high convergence, higher confidence)

        # Cross-encoder reranker score distribution
        "reranker_top_score": results[0].reranker_score,
        "reranker_score_spread": std_dev([r.reranker_score for r in results[:5]]),

        # Did BM25 and semantic search agree on top results?
        "retrieval_agreement": jaccard(bm25_top_5, semantic_top_5),
        # High agreement = query is well-matched to KB terminology
    }

    # Composite confidence level
    if signals["chunks_above_threshold"] >= 3 and signals["retrieval_agreement"] > 0.4:
        signals["confidence_level"] = "high"
    elif signals["chunks_above_threshold"] >= 1:
        signals["confidence_level"] = "moderate"
    else:
        signals["confidence_level"] = "low"

    return signals
```

### How to use computed confidence:

Inject the confidence assessment into the LLM's context so it calibrates its language appropriately:

```
## Retrieval Confidence Assessment
Confidence: HIGH — 4 of top 5 chunks reference Parker 12AT series return line filters.
BM25 and semantic search agree on 3 of top 5 results. Cross-encoder top score: 0.89.

→ You have strong grounding. Provide a specific recommendation with cited sources.
```

```
## Retrieval Confidence Assessment
Confidence: LOW — Only 1 chunk above relevance threshold. Top results span 4 different
product families with no convergence. Cross-encoder top score: 0.41.

→ Grounding is weak. Acknowledge limitations. Provide general guidance with caveats.
  Suggest the engineer provide more specific parameters to improve retrieval.
```

This gives Claude the information it needs to be appropriately confident or cautious, without asking it to self-assess (which it's bad at).

-----

## Front-Loaded Structured Intake: Reduce Gathering Phase LLM Calls

### The Problem

The gathering phase currently starts with an open-ended conversation. Claude asks predictable questions ("What fluid?" "What pressure?" "What application?") that burn 2-4 LLM round-trips on information that could be captured in a form.

### The Solution

Before the LLM conversation starts, present a lightweight structured intake in the UI:

```
┌─────────────────────────────────────────────────┐
│   Quick System Profile (optional — skip any)    │
│                                                 │
│ System type:     [ Mobile hydraulic       ▼ ]   │
│ Fluid:           [ Hydraulic oil          ▼ ]   │
│ Viscosity:       [ ISO VG 46              ▼ ]   │
│ Flow rate:       [ _______ ] LPM                │
│ Pressure:        [ _______ ] bar                │
│ Primary concern: [ ________________________ ]   │
│                                                 │
│   [ Start Consultation ]  [ Skip — just talk ]  │
└─────────────────────────────────────────────────┘
```

### What this changes in the architecture:

1. The frontend captures structured parameters BEFORE the first LLM call
2. These parameters are pre-injected into the gathering prompt context:

```
## Pre-Captured System Profile
The engineer has provided the following before the conversation started:
- System type: Mobile hydraulic
- Fluid: Hydraulic oil, ISO VG 46
- Flow rate: 120 LPM
- Operating pressure: 250 bar
- Primary concern: "rapid filter clogging on return line"

## Computed Fluid Properties (from reference database)
- Kinematic viscosity at 40°C: 46.0 cSt
- Kinematic viscosity at 80°C: ~8.5 cSt (estimated from VI)
- Specific gravity: 0.87

Acknowledge this information and proceed directly to diagnostic questions
specific to their concern. Do NOT re-ask for information already provided.
```

3. Claude's first message demonstrates that it already understands their system and goes straight to the interesting diagnostic questions
4. Gathering phase drops from 6-8 exchanges to 3-4

### Cost impact:

If an average consultation currently takes 8 LLM round-trips in gathering and 1-2 in answering, and structured intake eliminates 2-3 gathering round-trips, that's a 20-30% reduction in per-consultation LLM cost. At scale, this is significant.

### Implementation note:

This is NOT Sprint 1-6 work. It's a post-launch optimization. The current open-ended gathering flow works and should ship first. But the architecture should not preclude it — make sure gathered_parameters can be seeded from a structured form, not only from Claude's XML extraction.

-----

## Operating Context Portability: Cost Multiplier

When an engineer moves from one vertical to another within the same platform (e.g., filtration → pumps in FPS), the shared operating context transfers. This means:

- Fluid properties: already known (0 LLM calls to re-gather)
- System parameters: already known (0 LLM calls)
- Environment: already known (0 LLM calls)
- Constraints: already known (0 LLM calls)

The second vertical's gathering phase only needs vertical-specific parameters. Instead of 8 gathering exchanges, it needs 2-3. This is a ~60% cost reduction on the second consultation.

This compounds. An engineer consulting across 3 verticals in the same session pays full gathering cost once, then reduced cost twice. The platform model isn't just strategically valuable — it's operationally cheaper per consultation as usage deepens.

-----

## Pre-Computation Injection Pattern

This is the general pattern for every point where deterministic computation feeds into LLM context:

```python
async def build_answering_context(vertical_config, session, retrieval_result):
    """Build the complete context for the answering phase LLM call.

    All computable values are computed HERE, not by the LLM.
    The LLM receives pre-computed data and applies judgment/synthesis.
    """
    context = {}

    # 1. Retrieve from KB (already done)
    context["retrieved_chunks"] = retrieval_result.formatted_chunks

    # 2. Compute confidence (deterministic)
    context["confidence"] = compute_confidence(retrieval_result)

    # 3. Compute fluid properties (database lookup)
    fluid_params = session.gathered_parameters.get("fluid", {})
    if fluid_params.get("type") and fluid_params.get("viscosity_iso_grade"):
        context["computed_fluid_properties"] = lookup_fluid_properties(
            fluid_type=fluid_params["type"],
            viscosity_grade=fluid_params["viscosity_iso_grade"],
            operating_temp=fluid_params.get("temperature_range_c", {}).get("max")
        )

    # 4. Compute engineering values (formulas)
    system_params = session.gathered_parameters.get("system", {})
    if system_params.get("flow_rate_lpm") and context.get("computed_fluid_properties"):
        context["computed_engineering"] = {
            "reynolds_number": compute_reynolds(
                flow_rate=system_params["flow_rate_lpm"],
                viscosity=context["computed_fluid_properties"]["kinematic_viscosity_at_temp"],
                pipe_diameter=estimate_pipe_diameter(system_params["flow_rate_lpm"])
            ),
            "theoretical_delta_p": compute_delta_p(
                flow_rate=system_params["flow_rate_lpm"],
                viscosity=context["computed_fluid_properties"]["kinematic_viscosity_at_temp"],
                element_spec=retrieval_result.top_product_specs  # if available from KB
            )
        }

    # 5. Interpret standards (lookup tables)
    vertical_params = session.gathered_parameters.get("vertical_parameters", {})
    if vertical_params.get("target_cleanliness_iso4406"):
        context["interpreted_standards"] = interpret_iso4406(
            vertical_params["target_cleanliness_iso4406"]
        )

    # 6. Compute off-vertical relevance (embeddings, not LLM)
    context["off_vertical_signals"] = compute_vertical_relevance(
        session.recent_messages,
        vertical_config.platform.verticals
    )

    return context
```

The LLM call then receives all of this as structured context:

```
## Retrieved Knowledge Base Content
{context.retrieved_chunks}

## Retrieval Confidence
{context.confidence.summary}

## Computed Fluid Properties
{context.computed_fluid_properties.formatted}

## Computed Engineering Values
{context.computed_engineering.formatted}

## Standards Interpretation
{context.interpreted_standards.formatted}

## Your Task
Using the retrieved content and computed values above, synthesize a recommendation.
Cite sources for product recommendations. Use the computed values as given — do not
recalculate them.
```

-----

## Cost Monitoring

Track per-consultation LLM spend so you can identify optimization opportunities:

```sql
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    vertical_id TEXT,
    platform_id TEXT,
    phase TEXT,          -- 'gathering', 'answering', 'followup', 'title', 'other'
    model TEXT,          -- 'claude-sonnet-4-5-20250929', etc.
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost_usd REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

This lets you answer:
- What's the average cost per consultation by vertical?
- How many gathering round-trips before transition to answering?
- Does operating context portability actually reduce second-vertical costs?
- Are there verticals where gathering consistently takes too long?

-----

## Summary: Decision Rules for Claude Code

When implementing any new feature or modifying existing ones, apply these rules:

1. **Is it judgment, synthesis, or natural language generation?** → LLM. But pre-compute everything you can and inject it as context.
2. **Is it a lookup, calculation, or formula?** → Python function or database query. Never LLM.
3. **Is it classification or routing?** → Embedding similarity first. LLM only if embeddings are ambiguous.
4. **Is it self-assessment of quality/confidence?** → Computed metrics from retrieval signals. Never LLM self-report.
5. **Does the same predictable question get asked every time?** → Structured intake in UI. Don't burn LLM calls on predictable information gathering.
6. **Can the result be cached?** → Cache it. Fluid property lookups, ISO code interpretations, and standard reference data don't change between consultations.
7. **When in doubt:** Write the deterministic version first. If it produces inadequate results, escalate to LLM. The opposite direction (starting with LLM and optimizing later) rarely happens in practice because "it works" kills the motivation to optimize.
