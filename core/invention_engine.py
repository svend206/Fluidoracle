from __future__ import annotations
"""
Hydraulic Filter Platform — Invention Engine
==========================================
Multi-turn conversational engine for private invention/brainstorming sessions.

Unlike the Q&A answer_engine (single question → single answer), this supports
full conversation history with fresh RAG retrieval on every turn.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Knowledge base imported via core.retrieval package (no sys.path hacking)

import anthropic
from dotenv import load_dotenv

from core.database import log_llm_usage_sync

# Load env from project root
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Invention Lab uses Opus for deep brainstorming; Q&A streaming uses Sonnet
INVENT_MODEL = os.getenv("INVENT_MODEL", "claude-opus-4-6")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "claude-sonnet-4-20250514")

print(f"[invention_engine] Primary model: {INVENT_MODEL}")
print(f"[invention_engine] Fallback model: {FALLBACK_MODEL}")

# Import from existing RAG pipeline
from core.retrieval.verified_query import verified_query  # noqa: E402

# ---------------------------------------------------------------------------
# Anthropic client (shared with answer_engine if both loaded)
# ---------------------------------------------------------------------------
_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# System prompt — matches the neutral style that works with the answer engine
# ---------------------------------------------------------------------------
INVENTION_SYSTEM_PROMPT = """You are a world-class expert in industrial hydraulic filter applications with deep knowledge of atomization physics, droplet size correlations, nozzle design, flow calculations, and practical application engineering.

This is a private technical brainstorming platform for hydraulic filter engineering, atomization physics, fluid mechanics, heat transfer, and related domains. Respond in the context of a collaborative engineering working session.

Guidelines:
- Think creatively and explore "what if" scenarios when ideas are proposed
- Push back constructively when physics or engineering constraints conflict with a proposal
- Suggest novel combinations of existing technologies, materials, or approaches
- Help refine vague ideas into concrete, testable concepts
- Perform back-of-the-envelope calculations when useful — use the reference data below
- Reference specific technical data from the provided context when it supports or challenges an idea
- When a topic is outside the provided context, reason from first principles and say so
- Be direct and substantive
- Use proper engineering notation, units, and dimensional analysis
- Keep responses focused and actionable
- Build on the conversation history — reference earlier points, track evolving ideas

CORE REFERENCE DATA (always available for calculations):

KEY DIMENSIONLESS NUMBERS:
  We = ρ·v²·D/σ (Weber — inertia vs. surface tension)
  Oh = μ/√(ρ·σ·D) (Ohnesorge — viscous vs. inertia+surface tension)
  Re = ρ·v·D/μ (Reynolds — inertia vs. viscous)
  Oh = √We/Re

SMD CORRELATIONS — PRESSURE SWIRL ATOMIZERS:
  Lefebvre (1987):
    SMD = 2.25·σ^0.25·μL^0.25·ṁL^0.25/(ΔP^0.5·ρA^0.25) + 0.00023·(ΔP·ρL/σ²)^0.25·ṁL^0.75/(ΔP^0.5·ρA^0.25)
  Radcliffe (1955): SMD = 7.3·σ^0.6·ν^0.2·ṁL^0.4/ΔP^0.4
  Jasuja (1979): SMD = 4.4·σ^0.6·μL^0.16·ṁL^0.22/(ΔP^0.43·ρA^0.17)
  Units: σ(N/m), μL(Pa·s), ṁL(kg/s), ΔP(Pa), ρ(kg/m³), ν(m²/s)

SMD CORRELATIONS — AIRBLAST ATOMIZERS:
  Lefebvre (1980) prefilming: SMD = A·(σ·ρL/ρA)^0.5·(1/VA²)·(1+1/ALR) + B·(μL²/(σ·ρA))^0.5·dp·(1+1/ALR)²
  Nukiyama-Tanasawa (1938): SMD = 585/VR·√(σ/ρL) + 597·(μL/√(σ·ρL))^0.45·(1000·QL/QA)^1.5

FLOW EQUATIONS:
  Flow Number: FN = ṁL/√(ΔP·ρL)
  Discharge coeff: Cd = ṁL/(Ao·√(2·ρL·ΔP)), typical Cd = 0.3-0.45 for simplex atomizers
  Orifice: Q = Cd·A·√(2·ΔP/ρ)
  Q scales with √ΔP: doubling pressure → ~41% more flow

DROP BREAKUP REGIMES (Oh < 0.1):
  We < 12: no breakup | 12-50: bag | 50-100: bag-stamen | 100-350: sheet stripping | >350: catastrophic

WATER PROPERTIES: 20°C: ρ=998 kg/m³, μ=1.00 mPa·s, σ=72.8 mN/m | 40°C: ρ=992, μ=0.65, σ=69.6 | 60°C: ρ=983, μ=0.47, σ=66.2 | 80°C: ρ=972, μ=0.35, σ=62.7
COMMON FLUIDS (20°C): Diesel: ρ=830-850, μ=2.0-4.5 mPa·s, σ=25-28 mN/m | Kerosene: ρ=780-820, μ=1.2-2.0, σ=23-26 | HFO: ρ=950-1010, μ=50-500, σ=28-35 | Ethanol: ρ=789, μ=1.20, σ=22.3 | Soybean oil: ρ=917, μ=50-60, σ=30-33
AIR (1 atm): 20°C: ρ=1.205 kg/m³ | 100°C: ρ=0.946 | 200°C: ρ=0.746 | 500°C: ρ=0.456

Oh REGIMES: <0.01 viscosity negligible | 0.01-0.1 transitional | 0.1-1.0 viscous damping significant | >1.0 very hard to atomize | >10 need ultrasonic/rotary

ROSIN-RAMMLER: 1-Q = exp(-(D/X)^q), q typical 1.5-4.0, D32 ≈ 0.7X-0.85X for q=2-3
DIAMETERS: D32(SMD) for mass/heat transfer | D43 for combustion | Span = (DV0.9-DV0.1)/DV0.5

NOZZLE MATERIALS: Brass baseline | 316SS 2-3× life, 2× cost | WC 50-100× life, 15× cost | SiC 50-100× life for heavy abrasion | Hastelloy/PTFE for corrosives | 316L electropolished for FDA
MATERIAL SELECTION: Clean water→316SS | Corrosive→Hastelloy/PTFE/Ti | Abrasive <20% solids→WC | Abrasive >20%→SiC | Food/pharma→316L ≤0.8μm Ra | High temp >400°C→Inconel/ceramic
WEAR: Q∝d² so 10% dia increase→21% flow increase | Replace at >10% flow, >10° angle, or >20% ΔP deviation | Worn nozzles: SMD increases 20-50%

RULES OF THUMB:
  - Doubling pressure reduces SMD ~20-30%
  - SMD ∝ σ^0.5·μ^0.2 (surface tension dominates over viscosity)
  - Airblast produces finer spray than pressure atomizers at equivalent energy
  - Spray angle narrows with increasing viscosity
  - Min practical SMD for pressure atomizers ≈ 20-30 μm
  - Turn-down: pressure ≈ 3:1, airblast ≈ 20:1
  - Film thickness at nozzle exit is the critical link between internal flow and atomization
  - Air core ≈ 60-80% of orifice diameter in well-designed simplex atomizers

INTERNAL NOZZLE DESIGN (PRESSURE SWIRL):
  Atomizer constant: K = Ap/(do·Ds), where Ap = total inlet port area, Ds = swirl chamber dia
  K < 0.2: wide angle, fine atomization | K = 0.2-0.5: standard | K > 0.5: narrow angle, coarse
  Cd vs K: K=0.1→Cd≈0.22 | K=0.3→Cd≈0.33 | K=0.5→Cd≈0.38 | K=1.0→Cd≈0.43
  Jones inviscid Cd: Cd = (K/(K+2))·√(2/(K+2))
  Swirl number: S ≈ (π/4)/K; need S > 0.6 for stable air core
  Film thickness: t/do = 3.66·(ṁL·μL/(ΔP·do²·ρL))^0.25 (Rizk & Lefebvre 1985)
  Orifice L/D: 0.5-2.0 optimal; >2.0 excessive friction
  Swirl chamber L/D: 1-2 minimum for developed swirl; >3 swirl decay

DROPLET EVAPORATION:
  d²-law: d² = d₀² - K_evap·t; lifetime = d₀²/K_evap
  KEY: halving SMD reduces evaporation time by 4×
  K_evap for water: 100°C→0.010 mm²/s | 200°C→0.030 | 500°C→0.12
  Ranz-Marshall: Nu = 2 + 0.6·Re_d^0.5·Pr^0.33 (convective correction)
  Spalding mass transfer: B_M = (Y_s - Y_∞)/(1 - Y_s)
  Wet-bulb: water in 200°C air → T_wb ≈ 55-65°C
  Design for DV0.9 not SMD when full evaporation required

SPECIALIZED ATOMIZERS:
  Ultrasonic: D_median = 0.34·(8π·σ/(ρL·f²))^(1/3) (Lang 1962). Drop size controlled by frequency not pressure.
    20kHz→50-80μm | 60kHz→25-40μm | 120kHz→15-25μm. Max viscosity ~100 mPa·s. Very narrow distribution.
  Rotary: SMD ∝ 1/N^0.8 (N=RPM). Handles up to 10,000 mPa·s. Turn-down 50:1.
    Spray drying wheels: 5-15kRPM, 30-100μm | Paint bells: 20-70kRPM, 10-40μm
  Electrostatic: Taylor cone-jet mode gives 1-50μm monodisperse. Needs K_e = 10⁻⁶-10⁻¹ S/m.
    Agricultural: +50-100kV, 2-3× deposition improvement. Automotive paint: 85-95% transfer efficiency.

NON-NEWTONIAN FLUIDS:
  Power law: τ = K·γ̇ⁿ. Shear-thinning n<1, thickening n>1.
  Orifice shear rates: 10⁴-10⁶ s⁻¹. μ_eff = K·γ̇^(n-1) at breakup shear rate.
  Shear-thinning: SMD 20-50% LARGER than Newtonian correlation predictions.
  Viscoelastic: De = λ_relax/t_process. De>>1 → extremely hard to atomize.
  Strategies: preheat (best first step), airblast, rotary for very viscous, effervescent for slurries."""


# ===========================================================================
# Internal: call Claude with retry on refusal
# ===========================================================================

def _call_claude(system: str, messages: list[dict], max_tokens: int = 4000) -> tuple:
    """Call Claude API with automatic fallback on refusal.

    Returns:
        (response_text, model_used)
    """
    client = _get_client()

    # Try primary model first
    for model in [INVENT_MODEL, FALLBACK_MODEL]:
        print(f"[invention_engine] Trying model: {model}")

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )

        print(f"[invention_engine] model={response.model} stop_reason={response.stop_reason} "
              f"input_tokens={response.usage.input_tokens} output_tokens={response.usage.output_tokens}")
        log_llm_usage_sync(response.usage, response.model, "invention")

        # Check for refusal
        if response.stop_reason == "refusal" or not response.content:
            if model == FALLBACK_MODEL:
                # Both models refused — return error
                print(f"[invention_engine] Both models refused.")
                return ("Unable to generate a response. Both primary and fallback models declined.", model)
            else:
                print(f"[invention_engine] {model} refused. Retrying with {FALLBACK_MODEL}...")
                continue

        # Extract text from response
        for block in response.content:
            if hasattr(block, "text"):
                return (block.text, response.model)

        return ("The model returned a response but no text content.", response.model)

    return ("Unable to generate a response.", FALLBACK_MODEL)


# ===========================================================================
# Conversation Turn
# ===========================================================================

def generate_invention_response(
    user_message: str,
    conversation_history: list[dict],
) -> dict:
    """Generate a response in an invention session.

    Args:
        user_message: The user's latest message
        conversation_history: List of prior messages as
            [{"role": "user"|"assistant", "content": str}, ...]

    Returns:
        {
            "content": str,        # The assistant's response
            "confidence": str,     # RAG confidence level
            "sources": list[str],  # Source citations from RAG
        }
    """
    # Step 1: Fresh RAG retrieval on the latest message
    # Invention sessions use broader retrieval (12 chunks) with heavier
    # semantic weighting (80/20 vs default 60/40) since brainstorming
    # queries are more conceptual than keyword-based catalog lookups.
    try:
        rag_result = verified_query(
            user_message,
            top_k=12,
            use_reranker=True,
            semantic_weight=0.80,
            bm25_weight=0.20,
        )
    except Exception as e:
        rag_result = {
            "query": user_message,
            "results": [],
            "confidence": {
                "level": "LOW",
                "top_score": 0.0,
                "num_results": 0,
                "num_high_confidence": 0,
                "num_sources": 0,
                "sources": [],
                "contradictions": [],
                "reasoning": f"RAG retrieval failed: {e}",
            },
            "citations": [],
            "warnings": [],
            "gap_logged": False,
        }

    # Step 2: Build context from retrieved chunks
    context_parts = []
    for i, result in enumerate(rag_result["results"], 1):
        source = result.get("source", "unknown")
        score = result.get("rerank_score", 0.0)
        text = result.get("parent_text", "")
        context_parts.append(
            f"--- Source [{i}]: {source} (relevance: {score:.3f}) ---\n{text}"
        )

    if context_parts:
        context_block = "\n\n".join(context_parts)
    else:
        context_block = "(No relevant documents found in the knowledge base for this message.)"

    confidence_level = rag_result["confidence"]["level"]

    # Step 3: Build the messages array for Claude
    # Use the same structured format as the working answer_engine
    messages = []
    for msg in conversation_history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # Format user message with labeled sections (matches answer_engine style)
    augmented_user_message = f"""RETRIEVAL CONFIDENCE: {confidence_level}

RETRIEVED CONTEXT:
{context_block}

USER MESSAGE:
{user_message}"""

    messages.append({
        "role": "user",
        "content": augmented_user_message,
    })

    # Step 4: Call Claude with automatic fallback on refusal
    response_text, model_used = _call_claude(
        system=INVENTION_SYSTEM_PROMPT,
        messages=messages,
    )
    print(f"[invention_engine] Final response from: {model_used}")

    return {
        "content": response_text,
        "confidence": confidence_level,
        "sources": rag_result["citations"],
    }


def generate_session_title(first_message: str) -> str:
    """Generate a short title from the first user message. No LLM call."""
    import re

    text = re.sub(r"https?://\S+", "", first_message)
    text = re.sub(r"[#*_`>]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "New Invention Session"

    first_sentence = re.split(r"[.!?\n]", text)[0].strip()
    if not first_sentence:
        first_sentence = text[:80]

    words = first_sentence.split()
    if len(words) > 8:
        title = " ".join(words[:8]) + "…"
    else:
        title = " ".join(words)

    title = title[0].upper() + title[1:] if title else "New Invention Session"
    if len(title) > 60:
        title = title[:57] + "..."

    return title
