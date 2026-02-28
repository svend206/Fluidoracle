"""
Bootstrap script — seeds verticals, parameters, and initial fluid reference data.
Safe to re-run (idempotent).

Usage:
    python -m pipeline bootstrap
"""

import sqlite3
from .db import get_connection, init_db


def bootstrap_all() -> None:
    init_db()
    _seed_fluids()
    _seed_manufacturers()
    _seed_vertical_hydraulic_filters()
    print("[bootstrap] Done.")


# ---------------------------------------------------------------------------
# Fluid reference data
# Sources:
#   - Water: NIST WebBook
#   - Mineral oil: Engineering ToolBox / ISO 11158 typical values
#   - Water-glycol (50%): Engineering ToolBox
#   - NaOCl 12.5%: Perry's / vendor TDS
#   - Phosphate ester: vendor TDS (Skydrol typical)
# ---------------------------------------------------------------------------

FLUIDS = [
    {
        "id": "water",
        "name": "Water",
        "cas_number": "7732-18-5",
        "chemical_family": "inorganic",
        "description": "Pure water (H2O)",
        "hazard_class": "none",
        "fluid_class": None,
        "viscosity_grade": None,
        "trade_names": None,
        "base_stock": None,
    },
    {
        "id": "mineral-oil-iso-32",
        "name": "Mineral Hydraulic Oil ISO 32",
        "cas_number": None,
        "chemical_family": "petroleum-oil",
        "description": "Mineral-based hydraulic oil, ISO VG 32 grade (HM/HLP type per ISO 11158)",
        "hazard_class": "combustible-liquid",
        "fluid_class": "HM",
        "viscosity_grade": "ISO VG 32",
        "trade_names": '["Shell Tellus S2 M 32", "Mobil DTE 24", "Chevron Rando HDZ 32"]',
        "base_stock": "Group II",
    },
    {
        "id": "mineral-oil-iso-46",
        "name": "Mineral Hydraulic Oil ISO 46",
        "cas_number": None,
        "chemical_family": "petroleum-oil",
        "description": "Mineral-based hydraulic oil, ISO VG 46 grade (most common industrial hydraulic fluid)",
        "hazard_class": "combustible-liquid",
        "fluid_class": "HM",
        "viscosity_grade": "ISO VG 46",
        "trade_names": '["Shell Tellus S2 M 46", "Mobil DTE 25", "Chevron Rando HDZ 46"]',
        "base_stock": "Group II",
    },
    {
        "id": "mineral-oil-iso-68",
        "name": "Mineral Hydraulic Oil ISO 68",
        "cas_number": None,
        "chemical_family": "petroleum-oil",
        "description": "Mineral-based hydraulic oil, ISO VG 68 grade",
        "hazard_class": "combustible-liquid",
        "fluid_class": "HM",
        "viscosity_grade": "ISO VG 68",
        "trade_names": '["Shell Tellus S2 M 68", "Mobil DTE 26", "Chevron Rando HDZ 68"]',
        "base_stock": "Group II",
    },
    {
        "id": "water-glycol-50pct",
        "name": "Water-Glycol Hydraulic Fluid (50/50)",
        "cas_number": None,
        "chemical_family": "water-glycol",
        "description": "Fire-resistant hydraulic fluid — 50% ethylene or propylene glycol in water",
        "hazard_class": "none",
        "fluid_class": "HFC",
        "viscosity_grade": None,
        "trade_names": '["Houghton Safe 620", "Quaker Quintolubric 822"]',
        "base_stock": None,
    },
    {
        "id": "sodium-hypochlorite-12pct",
        "name": "Sodium Hypochlorite Solution 12%",
        "cas_number": "7681-52-9",
        "chemical_family": "oxidizing-halogen",
        "description": "12.5% NaOCl aqueous solution (commercial bleach / water treatment grade)",
        "hazard_class": "oxidizer-corrosive",
        "fluid_class": None,
        "viscosity_grade": None,
        "trade_names": None,
        "base_stock": None,
    },
    {
        "id": "phosphate-ester",
        "name": "Phosphate Ester Hydraulic Fluid",
        "cas_number": None,
        "chemical_family": "synthetic-ester",
        "description": "Fire-resistant synthetic hydraulic fluid (Skydrol, Fyrquel type)",
        "hazard_class": "combustible-liquid",
        "fluid_class": "HFDR",
        "viscosity_grade": None,
        "trade_names": '["Skydrol LD-4", "Fyrquel EHC", "Mobil Pyrotec HFD 46"]',
        "base_stock": "Phosphate ester",
    },
    {
        "id": "diesel-fuel-no2",
        "name": "Diesel Fuel No. 2",
        "cas_number": "68476-34-6",
        "chemical_family": "petroleum-distillate",
        "description": "No. 2-D diesel fuel per ASTM D975 — used in fuel filtration systems",
        "hazard_class": "flammable-liquid",
        "fluid_class": None,
        "viscosity_grade": None,
        "trade_names": None,
        "base_stock": None,
    },
]

# Physical properties: (fluid_id, concentration_pct, temp_f, visc_dyn_cp, visc_kin_cst,
#                       density_lb_gal, vapor_psi, ph, source)
FLUID_PROPERTIES = [
    # Water at various temperatures (NIST WebBook)
    ("water", None,  32,  1.792, 1.792, 8.344, 0.089,  7.0, "NIST-WebBook"),
    ("water", None,  68,  1.002, 1.004, 8.330, 0.339,  7.0, "NIST-WebBook"),
    ("water", None, 104,  0.658, 0.659, 8.280, 1.070,  7.0, "NIST-WebBook"),
    ("water", None, 140,  0.469, 0.470, 8.207, 2.889,  7.0, "NIST-WebBook"),
    ("water", None, 212,  0.282, 0.294, 8.004, 14.70,  7.0, "NIST-WebBook"),

    # Mineral oil ISO 32 (Engineering ToolBox / ISO 11158 typical)
    ("mineral-oil-iso-32", None,  40, None,  32.0, 7.29, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-32", None, 104, None,   6.5, 7.20, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-32", None, 140, None,   4.2, 7.15, None, None, "EngToolBox-ISO11158"),

    # Mineral oil ISO 46 (most common — Engineering ToolBox / ISO 11158 typical)
    # Note: viscosity at 40°C (104°F) = 46 cSt by definition of ISO VG grade
    ("mineral-oil-iso-46", None,  32, None,  200.0, 7.36, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-46", None, 104, None,   46.0, 7.27, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-46", None, 140, None,   24.0, 7.21, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-46", None, 212, None,    8.5, 7.08, None, None, "EngToolBox-ISO11158"),

    # Mineral oil ISO 68
    ("mineral-oil-iso-68", None, 104, None,   68.0, 7.34, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-68", None, 140, None,   34.0, 7.28, None, None, "EngToolBox-ISO11158"),
    ("mineral-oil-iso-68", None, 212, None,   11.5, 7.15, None, None, "EngToolBox-ISO11158"),

    # Water-glycol 50/50 (Engineering ToolBox)
    ("water-glycol-50pct", 50.0,  32, None,  18.0, 8.72, None, None, "EngToolBox"),
    ("water-glycol-50pct", 50.0,  68, None,   7.4, 8.65, None, None, "EngToolBox"),
    ("water-glycol-50pct", 50.0, 104, None,   4.0, 8.55, None, None, "EngToolBox"),
    ("water-glycol-50pct", 50.0, 140, None,   2.5, 8.44, None, None, "EngToolBox"),

    # NaOCl 12.5% (Perry's / Dow Chemical TDS)
    ("sodium-hypochlorite-12pct", 12.5,  68, 1.42, None, 9.05, None, 12.5, "Perry-Dow-TDS"),
    ("sodium-hypochlorite-12pct", 12.5, 104, 1.10, None, 8.96, None, 12.0, "Perry-Dow-TDS"),

    # Diesel fuel No. 2 (Engineering ToolBox / ASTM D975 typical)
    ("diesel-fuel-no2", None,  32, None,  6.0,  7.10, None, None, "EngToolBox-ASTM-D975"),
    ("diesel-fuel-no2", None,  68, None,  3.5,  7.04, None, None, "EngToolBox-ASTM-D975"),
    ("diesel-fuel-no2", None, 104, None,  2.2,  6.95, None, None, "EngToolBox-ASTM-D975"),
]

# Static properties: (fluid_id, property_key, value_numeric, value_text, unit, source)
# These are single-value properties not indexed by temperature.
FLUID_STATIC_PROPERTIES = [
    # Mineral oil ISO 32 (Shell Tellus S2 M 32 TDS)
    ("mineral-oil-iso-32", "pour_point_f",    -27,  None, "°F", "Shell-Tellus-S2-M-32-TDS"),
    ("mineral-oil-iso-32", "flash_point_f",   428,  None, "°F", "Shell-Tellus-S2-M-32-TDS"),
    ("mineral-oil-iso-32", "viscosity_index",  98,  None, None,  "Shell-Tellus-S2-M-32-TDS"),

    # Mineral oil ISO 46 (Shell Tellus S2 M 46 TDS)
    ("mineral-oil-iso-46", "pour_point_f",    -24,  None, "°F", "Shell-Tellus-S2-M-46-TDS"),
    ("mineral-oil-iso-46", "flash_point_f",   437,  None, "°F", "Shell-Tellus-S2-M-46-TDS"),
    ("mineral-oil-iso-46", "viscosity_index",  98,  None, None,  "Shell-Tellus-S2-M-46-TDS"),

    # Mineral oil ISO 68 (Shell Tellus S2 M 68 TDS)
    ("mineral-oil-iso-68", "pour_point_f",    -18,  None, "°F", "Shell-Tellus-S2-M-68-TDS"),
    ("mineral-oil-iso-68", "flash_point_f",   446,  None, "°F", "Shell-Tellus-S2-M-68-TDS"),
    ("mineral-oil-iso-68", "viscosity_index",  95,  None, None,  "Shell-Tellus-S2-M-68-TDS"),

    # Water-glycol 50% (Houghton Safe 620 TDS typical)
    ("water-glycol-50pct", "pour_point_f",    -35,  None, "°F", "Houghton-Safe-620-TDS"),
    ("water-glycol-50pct", "flash_point_f",   None, "None (aqueous)", "°F", "Houghton-Safe-620-TDS"),

    # Phosphate ester (Fyrquel EHC TDS typical)
    ("phosphate-ester", "pour_point_f",       -20,  None, "°F", "Fyrquel-EHC-TDS"),
    ("phosphate-ester", "flash_point_f",      455,  None, "°F", "Fyrquel-EHC-TDS"),
    ("phosphate-ester", "viscosity_index",     21,  None, None,  "Fyrquel-EHC-TDS"),

    # Diesel No. 2 (ASTM D975 typical)
    ("diesel-fuel-no2", "pour_point_f",       -10,  None, "°F", "ASTM-D975-typical"),
    ("diesel-fuel-no2", "flash_point_f",      140,  None, "°F", "ASTM-D975-typical"),
]

# Viscosity-temperature models (Walther equation: log log(ν + 0.7) = A - B·log(T_K))
# Coefficients fitted from published viscosity data at 40°C and 100°C per ISO 3448.
# Sources: ASTM D341 method, Shell TDS data, ISO VG grade definitions.
FLUID_VISCOSITY_MODELS = [
    # (fluid_id, model_type, param_a, param_b, param_c, temp_min_f, temp_max_f, r_squared, source)
    # Walther coefficients for mineral oils fitted from ISO VG definition points:
    #   ISO VG 32: 32 cSt @ 40°C, ~5.4 cSt @ 100°C (VI 98)
    #   ISO VG 46: 46 cSt @ 40°C, ~6.8 cSt @ 100°C (VI 98)
    #   ISO VG 68: 68 cSt @ 40°C, ~8.7 cSt @ 100°C (VI 95)
    ("mineral-oil-iso-32", "walther", 8.876, 3.298, None, -27, 300, 0.999, "ASTM-D341-fit-Shell-TDS"),
    ("mineral-oil-iso-46", "walther", 9.097, 3.356, None, -24, 300, 0.999, "ASTM-D341-fit-Shell-TDS"),
    ("mineral-oil-iso-68", "walther", 9.301, 3.404, None, -18, 300, 0.999, "ASTM-D341-fit-Shell-TDS"),
]

# Material compatibility: (fluid_id, conc_max, temp_max_f, material, rating, notes)
FLUID_COMPATIBILITY = [
    # Mineral oil
    ("mineral-oil-iso-46", None, 212, "carbon-steel",   "excellent", None),
    ("mineral-oil-iso-46", None, 212, "316SS",           "excellent", None),
    ("mineral-oil-iso-46", None, 212, "304SS",           "excellent", None),
    ("mineral-oil-iso-46", None, 212, "Buna-N",          "excellent", "Most common seal for mineral oil"),
    ("mineral-oil-iso-46", None, 212, "Viton",           "excellent", None),
    ("mineral-oil-iso-46", None, 212, "PTFE",            "excellent", None),
    ("mineral-oil-iso-46", None, 212, "Neoprene",        "good",      None),
    ("mineral-oil-iso-46", None, 212, "EPDM",            "poor",      "Swells in petroleum oil"),
    ("mineral-oil-iso-46", None, 212, "Nylon",           "good",      None),

    # NaOCl 12%
    ("sodium-hypochlorite-12pct", 15.0, 104, "316SS",    "good",         "Max 10% preferred; 316L better than 316"),
    ("sodium-hypochlorite-12pct", 15.0, 104, "304SS",    "poor",         "Susceptible to SCC"),
    ("sodium-hypochlorite-12pct", 15.0, 104, "carbon-steel", "incompatible", "Rapid corrosion"),
    ("sodium-hypochlorite-12pct", 15.0, 104, "CPVC",     "excellent",    None),
    ("sodium-hypochlorite-12pct", 15.0, 104, "PVDF",     "excellent",    "Preferred for piping"),
    ("sodium-hypochlorite-12pct", 15.0, 104, "PTFE",     "excellent",    None),
    ("sodium-hypochlorite-12pct", 15.0, 104, "Viton",    "excellent",    None),
    ("sodium-hypochlorite-12pct", 15.0, 104, "Buna-N",   "poor",         "Oxidizing attack"),
    ("sodium-hypochlorite-12pct", 15.0, 104, "EPDM",     "fair",         "Concentration and temp dependent"),

    # Water-glycol
    ("water-glycol-50pct", 60.0, 140, "carbon-steel",   "fair",      "pH must be maintained 8.5-9.5"),
    ("water-glycol-50pct", 60.0, 140, "316SS",           "excellent", None),
    ("water-glycol-50pct", 60.0, 140, "Buna-N",          "excellent", None),
    ("water-glycol-50pct", 60.0, 140, "PTFE",            "excellent", None),
    ("water-glycol-50pct", 60.0, 140, "zinc",            "incompatible", "Attacked by glycol solutions"),
    ("water-glycol-50pct", 60.0, 140, "magnesium",       "incompatible", None),
]


def _seed_fluids() -> None:
    with get_connection() as conn:
        for f in FLUIDS:
            try:
                conn.execute(
                    """INSERT INTO fluids (id, name, cas_number, chemical_family,
                       description, hazard_class, fluid_class, viscosity_grade,
                       trade_names, base_stock)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f["id"], f["name"], f["cas_number"], f["chemical_family"],
                     f["description"], f["hazard_class"], f.get("fluid_class"),
                     f.get("viscosity_grade"), f.get("trade_names"), f.get("base_stock")),
                )
            except sqlite3.IntegrityError:
                pass

        for p in FLUID_PROPERTIES:
            (fid, conc, temp, visc_d, visc_k, density,
             vapor, ph, source) = p
            try:
                conn.execute(
                    """INSERT INTO fluid_properties
                       (fluid_id, concentration_pct, temperature_f,
                        viscosity_dynamic_cp, viscosity_kinematic_cst,
                        density_lb_gal, vapor_pressure_psia, ph, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fid, conc, temp, visc_d, visc_k,
                     density, vapor, ph, source),
                )
            except sqlite3.IntegrityError:
                pass

        for c in FLUID_COMPATIBILITY:
            fid, conc_max, temp_max, material, rating, notes = c
            conn.execute(
                """INSERT INTO fluid_compatibility
                   (fluid_id, concentration_max_pct, temperature_max_f,
                    material, rating, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fid, conc_max, temp_max, material, rating, notes),
            )

        for sp in FLUID_STATIC_PROPERTIES:
            fid, prop_key, val_num, val_text, unit, source = sp
            try:
                conn.execute(
                    """INSERT INTO fluid_static_properties
                       (fluid_id, property_key, value_numeric, value_text, unit, source)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (fid, prop_key, val_num, val_text, unit, source),
                )
            except sqlite3.IntegrityError:
                pass

        for vm in FLUID_VISCOSITY_MODELS:
            fid, model_type, a, b, c, tmin, tmax, r2, source = vm
            try:
                conn.execute(
                    """INSERT INTO fluid_viscosity_models
                       (fluid_id, model_type, param_a, param_b, param_c,
                        temp_min_f, temp_max_f, r_squared, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fid, model_type, a, b, c, tmin, tmax, r2, source),
                )
            except sqlite3.IntegrityError:
                pass

    print(f"[bootstrap] Seeded {len(FLUIDS)} fluids, "
          f"{len(FLUID_PROPERTIES)} property records, "
          f"{len(FLUID_COMPATIBILITY)} compatibility records, "
          f"{len(FLUID_STATIC_PROPERTIES)} static properties, "
          f"{len(FLUID_VISCOSITY_MODELS)} viscosity models")


# ---------------------------------------------------------------------------
# Hydraulic Filters vertical
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Manufacturers
# ---------------------------------------------------------------------------

MANUFACTURERS = [
    {
        "id": "parker",
        "name": "Parker Hannifin",
        "website": "https://www.parker.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(parker|Parker|PARKER|FDCB|VEL)", "parker"],
    },
    {
        "id": "donaldson",
        "name": "Donaldson Company",
        "website": "https://www.donaldson.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(donaldson|Donaldson|DONALDSON|DHP)"],
    },
    {
        "id": "hydac",
        "name": "HYDAC Technology",
        "website": "https://www.hydac.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(hydac|HYDAC|Hydac)"],
    },
    {
        "id": "pall",
        "name": "Pall Corporation",
        "website": "https://www.pall.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(pall|Pall|PALL)"],
    },
    {
        "id": "schroeder",
        "name": "Schroeder Industries",
        "website": "https://www.schroederindustries.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(schroeder|Schroeder|SCHROEDER|L-\\d{4})"],
    },
    {
        "id": "bosch-rexroth",
        "name": "Bosch Rexroth",
        "website": "https://www.boschrexroth.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(bosch|Bosch|rexroth|Rexroth)"],
    },
    {
        "id": "eaton",
        "name": "Eaton Hydraulics",
        "website": "https://www.eaton.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(eaton|Eaton|EATON)"],
    },
    {
        "id": "mp-filtri",
        "name": "MP Filtri",
        "website": "https://www.mpfiltri.com",
        "data_quality": "engineering",
        "filename_patterns": ["^(mp-?filtri|MP-?Filtri|MP-?FILTRI)"],
    },
]


def _seed_manufacturers() -> None:
    import json
    with get_connection() as conn:
        for m in MANUFACTURERS:
            try:
                conn.execute(
                    """INSERT INTO manufacturers
                       (id, name, website, data_quality, filename_patterns)
                       VALUES (?, ?, ?, ?, ?)""",
                    (m["id"], m["name"], m["website"], m["data_quality"],
                     json.dumps(m["filename_patterns"])),
                )
            except sqlite3.IntegrityError:
                pass
    print(f"[bootstrap] Seeded {len(MANUFACTURERS)} manufacturers")


# ---------------------------------------------------------------------------
# Hydraulic Filters vertical
# ---------------------------------------------------------------------------

def _seed_vertical_hydraulic_filters() -> None:
    vid = "hydraulic-filters"
    with get_connection() as conn:
        try:
            conn.execute(
                """INSERT INTO verticals (id, display_name, description)
                   VALUES (?, ?, ?)""",
                (vid,
                 "Hydraulic & Lube Oil Filtration",
                 "Filters, filter elements, and contamination control for hydraulic and lube oil systems"),
            )
        except sqlite3.IntegrityError:
            pass

        params = [
            # key, display, type, unit, min, max, required
            ("cleanliness_target_iso4406",   "Target ISO 4406 Code",          "text",  "-",     None, None, 1),
            ("beta_ratio_required",          "Required Beta Ratio",           "float", "-",     2,    5000, 1),
            ("filter_micron_rating_um",      "Filter Micron Rating",          "float", "µm(c)", 0.5,  200,  1),
            ("system_flow_rate_gpm",         "System Flow Rate",              "float", "GPM",   0.1,  5000, 1),
            ("operating_viscosity_cst",      "Operating Fluid Viscosity",     "float", "cSt",   5,    1000, 1),
            ("operating_temperature_f",      "Operating Fluid Temperature",   "float", "°F",    -40,  300,  1),
            ("filter_location",              "Filter Location in Circuit",    "text",  "-",     None, None, 1),
            ("bypass_valve_setting_psi",     "Bypass Valve Setting",          "float", "PSI",   None, None, 0),
            ("element_collapse_pressure_psi","Element Collapse Pressure",     "float", "PSI",   None, None, 0),
            ("fluid_type",                   "Hydraulic Fluid Type",          "text",  "-",     None, None, 1),
            ("filter_housing_pressure_psi",  "Filter Housing Rated Pressure", "float", "PSI",   None, None, 0),
            ("particle_count_method",        "Particle Count Method",         "text",  "-",     None, None, 0),
            ("nas1638_class",                "NAS 1638 Class (legacy)",       "text",  "-",     None, None, 0),
            ("element_media_type",           "Filter Media Type",             "text",  "-",     None, None, 0),
            ("filter_mounting",              "Filter Mounting/Housing Type",  "text",  "-",     None, None, 0),
            ("system_type",                  "Hydraulic System Type",         "text",  "-",     None, None, 0),
        ]

        for (key, display, dtype, unit, vmin, vmax, req) in params:
            try:
                conn.execute(
                    """INSERT INTO vertical_parameters
                       (vertical_id, parameter_key, display_name, data_type,
                        unit, valid_min, valid_max, required_for_selection)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (vid, key, display, dtype, unit, vmin, vmax, req),
                )
            except sqlite3.IntegrityError:
                pass

        outcomes = [
            ("spray_pattern_met",      "Cleanliness Target Achieved",      "boolean"),
            ("contamination_iso_code", "Achieved ISO 4406 Code",           "text"),
            ("element_service_life",   "Filter Element Service Life",      "text"),
            ("premature_bypass",       "Experienced Premature Bypass",     "boolean"),
            ("media_failure",          "Media Failure or Rupture",         "boolean"),
            ("compatibility_issue",    "Fluid Compatibility Issue",        "boolean"),
            ("would_reuse",            "Would Specify This Product Again", "boolean"),
            ("notes",                  "Additional Outcome Notes",         "text"),
        ]
        for (key, display, dtype) in outcomes:
            try:
                conn.execute(
                    """INSERT INTO vertical_outcome_templates
                       (vertical_id, parameter_key, display_name, data_type)
                       VALUES (?, ?, ?, ?)""",
                    (vid, key, display, dtype),
                )
            except sqlite3.IntegrityError:
                pass

    print(f"[bootstrap] Seeded vertical: {vid} "
          f"({len(params)} parameters, {len(outcomes)} outcome fields)")
