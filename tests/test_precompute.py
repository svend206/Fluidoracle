#!/usr/bin/env python3
"""
Pre-Computation Engine Tests
=============================
Validates all deterministic computations from core/precompute.py.
Zero LLM calls — pure unit tests.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.precompute import (
    interpret_iso4406,
    lookup_viscosity,
    beta_to_efficiency,
    lookup_target_cleanliness,
    lookup_fluid_properties,
    compute_weber_number,
    compute_reynolds_number,
    classify_breakup_regime,
    build_precomputed_context,
)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


# ── ISO 4406 Interpretation ─────────────────────────────────────────────

def test_iso4406():
    print("\n── ISO 4406 Interpretation ──")

    r = interpret_iso4406("16/14/11")
    check("Parses 16/14/11", r is not None)
    check("Three channels", len(r["channels"]) == 3)
    check("First channel ≥4µm code=16", r["channels"][0]["code"] == 16)
    check("First channel 320-640", r["channels"][0]["particles_per_ml_min"] == 320)
    check("Third channel code=11", r["channels"][2]["code"] == 11)
    check("Third channel 10-20", r["channels"][2]["particles_per_ml_min"] == 10)

    # Edge cases
    check("Rejects garbage", interpret_iso4406("garbage") is None)
    check("Rejects 2-part code", interpret_iso4406("16/14") is None)
    check("Rejects empty", interpret_iso4406("") is None)

    # Boundary codes
    r2 = interpret_iso4406("28/6/6")
    check("Code 28 max = 2500000", r2["channels"][0]["particles_per_ml_max"] == 2_500_000)
    check("Code 6 min = 0.32", r2["channels"][1]["particles_per_ml_min"] == 0.32)


# ── Viscosity Lookup ────────────────────────────────────────────────────

def test_viscosity():
    print("\n── Viscosity Lookup ──")

    v = lookup_viscosity("VG46")
    check("VG46 found", v is not None)
    check("VG46 at 40C = 46", v["viscosity_at_40c_cst"] == 46)

    v2 = lookup_viscosity("VG46", 40)
    check("VG46 at 40C exact", v2["viscosity_at_temp_cst"] == 46)

    v3 = lookup_viscosity("VG46", 80)
    check("VG46 at 80C = 10", v3["viscosity_at_temp_cst"] == 10)

    # Interpolation
    v4 = lookup_viscosity("VG46", 50)
    check("VG46 at 50C interpolated", v4 is not None and "viscosity_at_temp_cst" in v4)
    check("VG46 at 50C between 20-46", 20 < v4["viscosity_at_temp_cst"] < 46,
          f"got {v4.get('viscosity_at_temp_cst')}")
    check("VG46 at 50C marked interpolated", v4.get("interpolated") is True)

    # Alternate formats
    v5 = lookup_viscosity("ISO VG 68")
    check("ISO VG 68 format accepted", v5 is not None and v5["grade"] == "VG68")

    v6 = lookup_viscosity("46")
    check("Bare '46' accepted", v6 is not None and v6["grade"] == "VG46")

    # Unknown grade
    check("Unknown grade returns None", lookup_viscosity("VG999") is None)


# ── Beta Ratio ──────────────────────────────────────────────────────────

def test_beta():
    print("\n── Beta Ratio → Efficiency ──")

    check("β1000 = 99.9%", beta_to_efficiency(1000) == 99.9)
    check("β200 = 99.5%", beta_to_efficiency(200) == 99.5)
    check("β100 = 99.0%", beta_to_efficiency(100) == 99.0)
    check("β2 = 50.0%", beta_to_efficiency(2) == 50.0)

    # Unlisted value — formula fallback
    eff = beta_to_efficiency(500)
    check("β500 computed = 99.8%", eff == 99.8, f"got {eff}")

    check("β1 returns None", beta_to_efficiency(1) is None)
    check("β0 returns None", beta_to_efficiency(0) is None)


# ── Target Cleanliness ──────────────────────────────────────────────────

def test_target_cleanliness():
    print("\n── Target Cleanliness Lookup ──")

    check("servo_valve basic", lookup_target_cleanliness("servo_valve") == "15/13/11")
    check("gear_pump basic", lookup_target_cleanliness("fixed_gear_pump") == "18/16/13")

    # Pressure-stratified
    check("servo <1500psi", lookup_target_cleanliness("servo_valve", 1000) == "16/14/12")
    check("servo 1500-2500", lookup_target_cleanliness("servo_valve", 2000) == "15/13/11")
    check("servo >2500psi", lookup_target_cleanliness("servo_valve", 3000) == "14/12/10")

    # Normalized input
    check("servo-valve with hyphen", lookup_target_cleanliness("servo-valve") == "15/13/11")
    check("Servo Valve with spaces", lookup_target_cleanliness("Servo Valve") == "15/13/11")

    # Unknown component
    check("unknown returns None", lookup_target_cleanliness("flux_capacitor") is None)


# ── Fluid Properties (Nozzle) ──────────────────────────────────────────

def test_fluid_properties():
    print("\n── Fluid Properties Lookup ──")

    w = lookup_fluid_properties("water")
    check("water found", w is not None)
    check("water density 998", w["density_kg_m3"] == 998)
    check("water viscosity 0.001", w["viscosity_pa_s"] == 0.001)
    check("water surface tension 0.0728", w["surface_tension_n_m"] == 0.0728)

    d = lookup_fluid_properties("diesel")
    check("diesel found", d is not None)
    check("diesel density 830", d["density_kg_m3"] == 830)

    # Partial match
    u = lookup_fluid_properties("urea")
    check("urea partial match", u is not None and u["fluid"] == "urea_32pct")

    # Unknown
    check("unknown returns None", lookup_fluid_properties("liquid_nitrogen") is None)


# ── Dimensionless Numbers ───────────────────────────────────────────────

def test_dimensionless():
    print("\n── Dimensionless Numbers ──")

    # We = ρ * v² * d / σ — water, 10 m/s, 1mm droplet
    we = compute_weber_number(10.0, 0.001, 998, 0.0728)
    check("Weber number water 10m/s 1mm", 1300 < we < 1400, f"got {we:.1f}")

    # Re = ρ * v * d / μ — water, 1 m/s, 10mm pipe
    re = compute_reynolds_number(1.0, 0.01, 998, 0.001)
    check("Reynolds number water", 9900 < re < 10000, f"got {re:.0f}")

    # Breakup regimes
    r = classify_breakup_regime(5)
    check("We=5 → no_breakup", r["regime"] == "no_breakup")

    r2 = classify_breakup_regime(30)
    check("We=30 → bag_breakup", r2["regime"] == "bag_breakup")

    r3 = classify_breakup_regime(500)
    check("We=500 → catastrophic", r3["regime"] == "catastrophic")


# ── Full Context Build ──────────────────────────────────────────────────

def test_full_context_build():
    print("\n── Full Context Build ──")

    # Filtration with rich parameters
    ctx = build_precomputed_context("hydraulic_filtration", {
        "viscosity_grade": "VG46",
        "operating_temperature": "80",
        "target_cleanliness": "16/14/11",
        "most_sensitive_component": "servo_valve",
        "pressure_psi": "3000",
        "required_beta": "1000",
    })
    check("Filtration context not empty", len(ctx) > 0)
    check("Contains VG46", "VG46" in ctx)
    check("Contains 10 cSt", "10 cSt" in ctx or "10.0 cSt" in ctx)
    check("Contains 320–640", "320" in ctx and "640" in ctx)
    check("Contains 99.9%", "99.9%" in ctx)
    check("Contains 14/12/10", "14/12/10" in ctx)
    check("Contains header", "Pre-Computed" in ctx)

    # Filtration with minimal parameters
    ctx2 = build_precomputed_context("hydraulic_filtration", {"viscosity_grade": "VG68"})
    check("Minimal filtration still works", "VG68" in ctx2)

    # Filtration with empty parameters
    ctx3 = build_precomputed_context("hydraulic_filtration", {})
    check("Empty params → empty context", ctx3 == "")

    # Nozzle
    ctx4 = build_precomputed_context("spray_nozzles", {"fluid": "water"})
    check("Nozzle context has density", "998" in ctx4)
    check("Nozzle context has surface tension", "0.0728" in ctx4)

    # Nozzle empty
    ctx5 = build_precomputed_context("spray_nozzles", {})
    check("Nozzle empty params → empty", ctx5 == "")

    # Unknown vertical
    ctx6 = build_precomputed_context("unknown_vertical", {"foo": "bar"})
    check("Unknown vertical → empty", ctx6 == "")

    # Nested parameters (some gathering signals nest params)
    ctx7 = build_precomputed_context("hydraulic_filtration", {
        "fluid": {"viscosity_grade": "VG32", "temperature": "60"},
    })
    check("Nested params found", "VG32" in ctx7)


# ── Deterministic Title Generation ──────────────────────────────────────

def test_titles():
    print("\n── Deterministic Title Generation ──")

    from core.consultation_engine import generate_session_title
    from core.invention_engine import generate_session_title as gen_invention_title

    t1 = generate_session_title("I have a contamination problem in my hydraulic return line filter")
    check("Consultation title not empty", len(t1) > 0)
    check("No LLM call (under 60 chars)", len(t1) <= 60)
    check("Starts with capital", t1[0].isupper())
    check("Contains 'contamination' or 'hydraulic'", "contamination" in t1.lower() or "hydraulic" in t1.lower())

    t2 = generate_session_title("")
    check("Empty message → default", "Consultation" in t2 or "New" in t2)

    t3 = generate_session_title("x " * 100)
    check("Very long message truncated", len(t3) <= 60)

    t4 = gen_invention_title("Can we design a self-cleaning filter?")
    check("Invention title works", len(t4) > 0 and "self-cleaning" in t4.lower())

    t5 = gen_invention_title("")
    check("Invention empty → default", "Invention" in t5 or "New" in t5)


# ── LLM Usage Table ─────────────────────────────────────────────────────

def test_llm_usage():
    print("\n── LLM Usage Tracking ──")

    import asyncio
    import sqlite3
    import tempfile
    import os
    from core.database import set_db_path, init_db, log_llm_usage_sync

    # Use a temp DB
    tmp = tempfile.mktemp(suffix=".db")
    set_db_path(tmp)
    asyncio.run(init_db())

    class FakeUsage:
        input_tokens = 2000
        output_tokens = 500

    log_llm_usage_sync(FakeUsage(), "claude-sonnet-4-5-20250929", "gathering",
                       session_id="test-s1", vertical_id="hydraulic_filtration", platform_id="fps")
    log_llm_usage_sync(FakeUsage(), "claude-sonnet-4-5-20250929", "answering",
                       session_id="test-s1", vertical_id="hydraulic_filtration", platform_id="fps")

    conn = sqlite3.connect(tmp)
    rows = conn.execute("SELECT phase, model, input_tokens, output_tokens, estimated_cost_usd FROM llm_usage").fetchall()
    check("Two rows inserted", len(rows) == 2)
    check("First row is gathering", rows[0][0] == "gathering")
    check("Second row is answering", rows[1][0] == "answering")
    check("Input tokens correct", rows[0][2] == 2000)
    check("Output tokens correct", rows[0][3] == 500)

    # Cost calculation: (2000 * 3.0 + 500 * 15.0) / 1_000_000 = 0.0135
    check("Cost calculation correct", abs(rows[0][4] - 0.0135) < 0.0001, f"got {rows[0][4]}")

    # Verify it doesn't crash on missing model pricing
    log_llm_usage_sync(FakeUsage(), "unknown-model-xyz", "other")
    rows2 = conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()
    check("Unknown model still logs", rows2[0] == 3)

    conn.close()
    os.unlink(tmp)


# ── Vertical Loader ─────────────────────────────────────────────────────

def test_vertical_loader():
    print("\n── Vertical Loader ──")

    from core.vertical_loader import load_platform

    fps = load_platform("fps")
    check("FPS loads", fps is not None)
    check("FPS id = fps", fps.platform_id == "fps")
    check("FPS has hydraulic_filtration", "hydraulic_filtration" in fps.verticals)

    hf = fps.verticals["hydraulic_filtration"]
    check("HF gathering prompt populated", len(hf.gathering_prompt) > 100)
    check("HF answering prompt populated", len(hf.answering_prompt) > 100)
    check("HF has application domains", len(hf.application_domains) > 0)
    check("HF has example questions", len(hf.example_questions) > 0)
    check("HF child collection set", hf.child_collection == "hydraulic_filtration-children")
    check("HF parent collection set", hf.parent_collection == "hydraulic_filtration-parents")

    fds = load_platform("fds")
    check("FDS loads", fds is not None)
    check("FDS has spray_nozzles", "spray_nozzles" in fds.verticals)

    sn = fds.verticals["spray_nozzles"]
    check("SN gathering prompt populated", len(sn.gathering_prompt) > 100)
    check("SN answering prompt populated", len(sn.answering_prompt) > 100)
    check("SN has application domains", len(sn.application_domains) > 0)
    check("SN child collection set", sn.child_collection == "spray_nozzles-children")

    # Verify isolation — different collections
    check("Collections differ", hf.child_collection != sn.child_collection)
    check("BM25 paths differ", hf.bm25_index_path != sn.bm25_index_path)

    # Bad platform
    try:
        load_platform("nonexistent")
        check("Bad platform raises", False, "no exception raised")
    except ValueError:
        check("Bad platform raises ValueError", True)


# ── Run All ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("FLUIDORACLE UNIT TEST SUITE")
    print("Zero LLM calls — pure deterministic tests")
    print("=" * 60)

    test_iso4406()
    test_viscosity()
    test_beta()
    test_target_cleanliness()
    test_fluid_properties()
    test_dimensionless()
    test_full_context_build()
    test_titles()
    test_llm_usage()
    test_vertical_loader()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        print("❌ SOME TESTS FAILED")
    else:
        print("✅ ALL TESTS PASSED")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)
