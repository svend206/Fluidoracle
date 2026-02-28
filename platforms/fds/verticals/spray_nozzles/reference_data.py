"""
Spray Nozzles — Core Reference Data

Structured reference tables for programmatic use.
The full prose reference data (SMD correlations, fluid properties,
evaporation models, etc.) lives in answering_prompt.md and is
injected into the LLM system prompt.

Sources: Lefebvre & McDonell (2017), Bayvel & Orzechowski,
ILASS proceedings, manufacturer catalogs.
"""
from __future__ import annotations


# Fluid properties at 20°C for common spray fluids
FLUID_PROPERTIES = {
    "water": {
        "density_kg_m3": 998,
        "viscosity_pa_s": 0.001,
        "surface_tension_n_m": 0.0728,
        "notes": "Reference fluid for most correlations",
    },
    "diesel": {
        "density_kg_m3": 830,
        "viscosity_pa_s": 0.003,
        "surface_tension_n_m": 0.025,
        "notes": "Typical #2 diesel",
    },
    "kerosene": {
        "density_kg_m3": 800,
        "viscosity_pa_s": 0.0016,
        "surface_tension_n_m": 0.023,
        "notes": "Jet-A equivalent",
    },
    "heavy_fuel_oil": {
        "density_kg_m3": 950,
        "viscosity_pa_s": 0.080,
        "surface_tension_n_m": 0.030,
        "notes": "At ~80°C (preheated for atomization)",
    },
    "milk_whole": {
        "density_kg_m3": 1030,
        "viscosity_pa_s": 0.002,
        "surface_tension_n_m": 0.042,
        "notes": "Common spray drying feed; varies with solids",
    },
    "urea_32pct": {
        "density_kg_m3": 1090,
        "viscosity_pa_s": 0.0015,
        "surface_tension_n_m": 0.065,
        "notes": "AdBlue/DEF for SCR systems",
    },
}


# Drop breakup regimes (Weber number based)
BREAKUP_REGIMES = {
    "no_breakup": {"We_range": (0, 12), "description": "Droplet oscillates but does not break"},
    "bag_breakup": {"We_range": (12, 50), "description": "Thin bag forms and bursts"},
    "multimode": {"We_range": (50, 100), "description": "Bag + stamen breakup"},
    "sheet_stripping": {"We_range": (100, 350), "description": "Sheet stripped from periphery"},
    "catastrophic": {"We_range": (350, float("inf")), "description": "Wave instabilities cause rapid fragmentation"},
}


# Nozzle type selection guide
NOZZLE_TYPES = {
    "full_cone": {
        "pattern": "Full cone (solid)",
        "typical_smd_um": (100, 1000),
        "typical_angle_deg": (15, 120),
        "pressure_range_bar": (0.5, 70),
        "best_for": ["cooling", "washing", "dust suppression", "fire protection"],
        "turndown": "~3:1 (pressure-based)",
    },
    "hollow_cone": {
        "pattern": "Hollow cone",
        "typical_smd_um": (50, 300),
        "typical_angle_deg": (30, 120),
        "pressure_range_bar": (1, 100),
        "best_for": ["spray drying", "humidification", "gas cooling", "chemical injection"],
        "turndown": "~3:1 (pressure-based)",
    },
    "flat_fan": {
        "pattern": "Flat fan",
        "typical_smd_um": (100, 800),
        "typical_angle_deg": (15, 110),
        "pressure_range_bar": (0.5, 500),
        "best_for": ["coating", "descaling", "cleaning", "agricultural"],
        "turndown": "~3:1 (pressure-based)",
    },
    "air_atomizing": {
        "pattern": "Various (typically full/hollow cone)",
        "typical_smd_um": (10, 100),
        "typical_angle_deg": (15, 80),
        "pressure_range_bar": (0.2, 7),
        "best_for": ["fine mist", "coating", "humidification", "chemical injection"],
        "turndown": "~10:1 (air-assisted)",
    },
    "solid_stream": {
        "pattern": "Solid stream / coherent jet",
        "typical_smd_um": None,  # Not applicable — no atomization
        "typical_angle_deg": (0, 5),
        "pressure_range_bar": (1, 700),
        "best_for": ["descaling", "cutting", "tank cleaning (impact)"],
        "turndown": "~3:1",
    },
}


# Material selection guide
NOZZLE_MATERIALS = {
    "brass": {
        "max_temp_c": 200,
        "corrosion_resistance": "low",
        "erosion_resistance": "low",
        "cost": "low",
        "notes": "Water-only, non-abrasive, short-life OK",
    },
    "stainless_303": {
        "max_temp_c": 800,
        "corrosion_resistance": "medium",
        "erosion_resistance": "medium",
        "cost": "medium",
        "notes": "General purpose industrial",
    },
    "stainless_316": {
        "max_temp_c": 800,
        "corrosion_resistance": "high",
        "erosion_resistance": "medium",
        "cost": "medium-high",
        "notes": "Chemical, food/pharma, marine",
    },
    "hastelloy_c276": {
        "max_temp_c": 1000,
        "corrosion_resistance": "very high",
        "erosion_resistance": "medium",
        "cost": "high",
        "notes": "Aggressive chemicals, HCl, H2SO4",
    },
    "tungsten_carbide": {
        "max_temp_c": 500,
        "corrosion_resistance": "medium",
        "erosion_resistance": "very high",
        "cost": "high",
        "notes": "Abrasive slurries, long life critical",
    },
    "ceramic_al2o3": {
        "max_temp_c": 1500,
        "corrosion_resistance": "high",
        "erosion_resistance": "very high",
        "cost": "medium-high",
        "notes": "High temp, abrasive, but brittle",
    },
    "ptfe_pvdf": {
        "max_temp_c": 150,
        "corrosion_resistance": "very high",
        "erosion_resistance": "low",
        "cost": "medium",
        "notes": "Strong acids/bases, no abrasives",
    },
}
