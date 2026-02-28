"""
Fluidoracle — Pre-Computation Engine
======================================
Deterministic computations that run BEFORE the LLM answering call.
Results are injected as context so Claude reasons with pre-computed
numbers instead of deriving them.

See docs/compute-strategy.md for the full decision matrix.
"""
from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Hydraulic Filtration computations
# ---------------------------------------------------------------------------

def interpret_iso4406(code_str: str) -> dict | None:
    """Interpret an ISO 4406 cleanliness code into particle counts.

    Args:
        code_str: e.g. "16/14/11"

    Returns:
        Dict with per-size interpretation, or None if unparseable.
    """
    from platforms.fps.verticals.hydraulic_filtration.reference_data import ISO_4406_CODES

    parts = [p.strip() for p in code_str.split("/")]
    if len(parts) != 3:
        return None

    sizes = ["≥4µm(c)", "≥6µm(c)", "≥14µm(c)"]
    result = {"raw": code_str, "channels": []}
    try:
        for i, code_val in enumerate(int(p) for p in parts):
            bounds = ISO_4406_CODES.get(code_val)
            if bounds:
                lo, hi = bounds
                result["channels"].append({
                    "size": sizes[i],
                    "code": code_val,
                    "particles_per_ml_min": lo,
                    "particles_per_ml_max": hi,
                })
            else:
                result["channels"].append({
                    "size": sizes[i],
                    "code": code_val,
                    "particles_per_ml_min": None,
                    "particles_per_ml_max": None,
                })
    except (ValueError, TypeError):
        return None

    return result


def lookup_viscosity(grade: str, temp_c: float | None = None) -> dict | None:
    """Look up viscosity for an ISO VG grade, optionally at a specific temperature.

    Returns dict with viscosity data, or None if grade unknown.
    """
    from platforms.fps.verticals.hydraulic_filtration.reference_data import VISCOSITY_TEMPERATURE

    grade_key = grade.upper().replace("ISO ", "").replace(" ", "")
    if not grade_key.startswith("VG"):
        grade_key = f"VG{grade_key}"

    data = VISCOSITY_TEMPERATURE.get(grade_key)
    if not data:
        return None

    result = {"grade": grade_key, "viscosity_at_40c_cst": data.get(40)}

    if temp_c is not None:
        # Find bracketing temperatures and interpolate (log-log)
        temps = sorted(data.keys())
        if temp_c in data:
            result["viscosity_at_temp_cst"] = data[temp_c]
            result["temperature_c"] = temp_c
        else:
            # Linear interpolation in log space (Walther equation approximation)
            lower = max((t for t in temps if t <= temp_c), default=None)
            upper = min((t for t in temps if t >= temp_c), default=None)
            if lower is not None and upper is not None and lower != upper:
                v_lo = math.log(data[lower])
                v_hi = math.log(data[upper])
                frac = (temp_c - lower) / (upper - lower)
                result["viscosity_at_temp_cst"] = round(math.exp(v_lo + frac * (v_hi - v_lo)), 1)
                result["temperature_c"] = temp_c
                result["interpolated"] = True

    return result


def beta_to_efficiency(beta: int | float) -> float | None:
    """Convert a beta ratio to filtration efficiency percentage."""
    from platforms.fps.verticals.hydraulic_filtration.reference_data import BETA_EFFICIENCY

    if beta in BETA_EFFICIENCY:
        return BETA_EFFICIENCY[beta]
    if beta > 1:
        return round((1 - 1 / beta) * 100, 2)
    return None


def lookup_target_cleanliness(component: str, pressure_psi: float | None = None) -> str | None:
    """Look up recommended cleanliness target for a component type."""
    from platforms.fps.verticals.hydraulic_filtration.reference_data import (
        TARGET_CLEANLINESS_BY_COMPONENT,
        TARGET_CLEANLINESS_BY_PRESSURE,
    )

    # Normalize component name
    comp_key = component.lower().replace(" ", "_").replace("-", "_")

    # Try pressure-stratified first
    if pressure_psi is not None and comp_key in TARGET_CLEANLINESS_BY_PRESSURE:
        pressure_map = TARGET_CLEANLINESS_BY_PRESSURE[comp_key]
        if pressure_psi < 1500:
            return pressure_map.get("<1500psi")
        elif pressure_psi <= 2500:
            return pressure_map.get("1500-2500psi")
        else:
            return pressure_map.get(">2500psi")

    # Fall back to general table
    return TARGET_CLEANLINESS_BY_COMPONENT.get(comp_key)


# ---------------------------------------------------------------------------
# Spray Nozzle computations
# ---------------------------------------------------------------------------

def compute_weber_number(
    velocity_m_s: float,
    droplet_diameter_m: float,
    density_kg_m3: float,
    surface_tension_n_m: float,
) -> float:
    """Compute Weber number: We = ρ * v² * d / σ"""
    return density_kg_m3 * velocity_m_s**2 * droplet_diameter_m / surface_tension_n_m


def compute_reynolds_number(
    velocity_m_s: float,
    diameter_m: float,
    density_kg_m3: float,
    viscosity_pa_s: float,
) -> float:
    """Compute Reynolds number: Re = ρ * v * d / μ"""
    return density_kg_m3 * velocity_m_s * diameter_m / viscosity_pa_s


def lookup_fluid_properties(fluid_name: str) -> dict | None:
    """Look up spray fluid properties by name."""
    from platforms.fds.verticals.spray_nozzles.reference_data import FLUID_PROPERTIES

    key = fluid_name.lower().replace(" ", "_").replace("-", "_")
    # Try exact match first, then partial
    if key in FLUID_PROPERTIES:
        return {"fluid": fluid_name, **FLUID_PROPERTIES[key]}
    for k, v in FLUID_PROPERTIES.items():
        if key in k or k in key:
            return {"fluid": k, **v}
    return None


def classify_breakup_regime(weber_number: float) -> dict | None:
    """Classify droplet breakup regime from Weber number."""
    from platforms.fds.verticals.spray_nozzles.reference_data import BREAKUP_REGIMES

    for regime, info in BREAKUP_REGIMES.items():
        lo, hi = info["We_range"]
        if lo <= weber_number < hi:
            return {"regime": regime, "We": round(weber_number, 1), "description": info["description"]}
    return None


# ---------------------------------------------------------------------------
# Generic: Build pre-computed context block for LLM injection
# ---------------------------------------------------------------------------

def build_precomputed_context(
    vertical_id: str,
    gathered_parameters: dict[str, Any],
) -> str:
    """Build a formatted context block of pre-computed values from gathered parameters.

    Returns a string ready for injection into the answering prompt.
    Empty string if nothing could be computed.
    """
    lines: list[str] = []

    if vertical_id == "hydraulic_filtration":
        lines = _precompute_filtration(gathered_parameters)
    elif vertical_id == "spray_nozzles":
        lines = _precompute_nozzles(gathered_parameters)

    if not lines:
        return ""

    return "## Pre-Computed Engineering Values (use as given — do not recalculate)\n" + "\n".join(lines)


def _precompute_filtration(params: dict) -> list[str]:
    """Pre-compute values for hydraulic filtration consultations."""
    lines: list[str] = []

    # Viscosity lookup
    fluid_grade = _extract(params, "viscosity_grade", "fluid_viscosity", "iso_vg", "viscosity")
    if fluid_grade:
        # Try to extract temperature
        temp = _extract_number(params, "temperature", "operating_temperature", "temp_c", "max_temperature")
        visc = lookup_viscosity(str(fluid_grade), temp)
        if visc:
            lines.append(f"- Fluid: {visc['grade']}, viscosity at 40°C: {visc['viscosity_at_40c_cst']} cSt")
            if "viscosity_at_temp_cst" in visc:
                interp = " (interpolated)" if visc.get("interpolated") else ""
                lines.append(f"- Viscosity at {visc['temperature_c']}°C: {visc['viscosity_at_temp_cst']} cSt{interp}")

    # ISO 4406 interpretation
    cleanliness = _extract(params, "target_cleanliness", "cleanliness_target", "iso_4406", "cleanliness")
    if cleanliness and "/" in str(cleanliness):
        interp = interpret_iso4406(str(cleanliness))
        if interp and interp["channels"]:
            lines.append(f"- Target cleanliness {cleanliness} means:")
            for ch in interp["channels"]:
                if ch["particles_per_ml_min"] is not None:
                    lines.append(
                        f"  • {ch['size']}: {ch['particles_per_ml_min']:,.0f}–"
                        f"{ch['particles_per_ml_max']:,.0f} particles/mL"
                    )

    # Component-based cleanliness recommendation
    component = _extract(params, "component", "most_sensitive_component", "critical_component")
    if component:
        pressure_psi = _extract_number(params, "pressure_psi", "operating_pressure_psi", "pressure")
        target = lookup_target_cleanliness(str(component), pressure_psi)
        if target:
            lines.append(f"- Recommended cleanliness for {component}: {target} (ISO 4406)")

    # Beta ratio interpretation
    beta = _extract(params, "beta_ratio", "required_beta", "filtration_ratio")
    if beta:
        try:
            beta_val = float(str(beta).replace(",", ""))
            eff = beta_to_efficiency(beta_val)
            if eff is not None:
                lines.append(f"- β ratio {beta_val} = {eff}% capture efficiency")
        except (ValueError, TypeError):
            pass

    return lines


def _precompute_nozzles(params: dict) -> list[str]:
    """Pre-compute values for spray nozzle consultations."""
    lines: list[str] = []

    # Fluid property lookup
    fluid = _extract(params, "fluid", "liquid", "spray_fluid", "medium")
    if fluid:
        props = lookup_fluid_properties(str(fluid))
        if props:
            lines.append(f"- Fluid: {props['fluid']}")
            lines.append(f"  • Density: {props['density_kg_m3']} kg/m³")
            lines.append(f"  • Viscosity: {props['viscosity_pa_s']} Pa·s")
            lines.append(f"  • Surface tension: {props['surface_tension_n_m']} N/m")
            if props.get("notes"):
                lines.append(f"  • Note: {props['notes']}")

    return lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract(params: dict, *keys: str) -> Any | None:
    """Extract a value from gathered parameters, trying multiple key names.
    Searches top-level and one level of nesting."""
    for key in keys:
        if key in params:
            return params[key]
    # Search one level deep
    for v in params.values():
        if isinstance(v, dict):
            for key in keys:
                if key in v:
                    return v[key]
    return None


def _extract_number(params: dict, *keys: str) -> float | None:
    """Extract a numeric value, parsing strings if needed."""
    val = _extract(params, *keys)
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").split()[0])
    except (ValueError, TypeError, IndexError):
        return None
