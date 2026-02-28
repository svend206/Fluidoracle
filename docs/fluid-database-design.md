# Fluid Database Design

**Date:** 2026-02-26
**Author:** openclaw
**Status:** Draft — awaiting Erik's review

---

## 1. What a Complete Fluid Record Looks Like

A fluid in the Oracle platform serves one purpose: resolving "what fluid is in this system?" into the physical properties needed for component selection across all verticals. A complete record has five layers:

### Identity
- **Name** (display name, e.g., "Mineral Hydraulic Oil ISO 46")
- **Slug** (machine ID, e.g., `mineral-oil-iso-46`)
- **CAS number** (when applicable — pure compounds only; commercial formulations don't have one)
- **Chemical family** (taxonomy for grouping: `petroleum-oil`, `synthetic-ester`, `water-glycol`, `vegetable-oil`, etc.)
- **Fluid class** (industry standard classification: ISO 6743/4 for hydraulic fluids, ISO 6743/9 for lubricants)
- **Hazard classification** (GHS-based: flammability, corrosivity, toxicity)
- **Common trade names / OEM cross-references** (e.g., Mobil DTE 25 = ISO 46 mineral oil)

### Physical Properties (at conditions)
Every property is a function of temperature and (for solutions) concentration. There is no "the viscosity of ISO 46 oil" — there is only "the viscosity of ISO 46 oil at 104°F."

Core properties needed across verticals:
| Property | Unit | Who Needs It | Source Tier |
|---|---|---|---|
| Kinematic viscosity | cSt (mm²/s) | Filters (ΔP, bypass), pumps (efficiency, cavitation), nozzles (atomization) | **All verticals** |
| Dynamic viscosity | cP (mPa·s) | Nozzles (flow calculations), pumps (torque) | Most verticals |
| Density | lb/gal or kg/m³ | All (mass flow, pressure calculations) | All |
| Vapor pressure | psia or kPa | Pumps (NPSH/cavitation), nozzles (flashing) | Pumps, nozzles |
| Specific heat | BTU/lb·°F or kJ/kg·K | Heat exchangers, coolers | Thermal management |
| Thermal conductivity | BTU/hr·ft·°F or W/m·K | Heat exchangers | Thermal management |
| Surface tension | dyn/cm or mN/m | Nozzles (droplet formation, spray pattern) | Nozzles primarily |
| Bulk modulus | PSI or GPa | Filters (water hammer), pumps (response time), valves (control stability) | Hydraulic systems |
| Pour point | °F or °C | All (cold start, low-temp operation) | All |
| Flash point | °F or °C | All (fire safety classification) | All |
| Air release value | minutes (per ISO 9120) | Filters (foaming), pumps (cavitation from entrained air) | Hydraulic systems |
| Foaming tendency | mL foam (ASTM D892) | Filters, reservoirs | Hydraulic systems |
| Water saturation point | ppm at temperature | Filters (water removal), condition monitoring | Hydraulic systems |
| pH | — | Filters (media compatibility), seals, piping | Aqueous fluids only |
| Electrical conductivity | µS/cm | ESD-sensitive applications | Specialized |

### Material Compatibility
- What the fluid does to the materials it contacts: seals (Buna-N, Viton, EPDM, PTFE), metals (carbon steel, 316SS, aluminum, brass, zinc), plastics (nylon, polycarbonate, CPVC, PVDF).
- Always conditional on concentration and temperature.
- Rating scale: `excellent`, `good`, `fair`, `poor`, `incompatible`.

### Condition Curves (Temperature-Viscosity Relationship)
The most important fluid property for component selection is viscosity, and viscosity varies exponentially with temperature. Rather than storing discrete points, the system should also store (when available) the parameters for standard viscosity-temperature models:

- **Walther equation** (ASTM D341): `log log(ν + 0.7) = A − B·log(T)` — the industry standard for petroleum oils. Two parameters (A, B) predict viscosity at any temperature.
- **Andrade equation**: `ln(µ) = A + B/T` — simpler, adequate for narrow temperature ranges.

Storing model coefficients alongside discrete measured points allows interpolation at any operating temperature, which is far more useful than lookup tables.

### Fluid Mixtures and Blending
Some real-world systems don't run a single cataloged fluid:
- **Diluted solutions** (NaOCl at 6% vs 12%) — concentration is the primary variable.
- **Contaminated fluids** (hydraulic oil with 0.1% water ingress) — the contamination is the interesting part for filter selection.
- **Blended oils** (mixing ISO 32 and ISO 68 for intermediate viscosity) — less common but real.

The current schema handles the first case (via `concentration_pct`) but not the other two.

---

## 2. Property Taxonomy

### Tier 1: Universal Properties (every fluid needs these)
| Property | Why | Precision Needed |
|---|---|---|
| Kinematic viscosity vs. temperature | Drives component sizing across all verticals | ±5% at 3+ temperatures spanning operating range |
| Density vs. temperature | Mass flow, pressure calculations | ±1% at 2+ temperatures |
| Chemical family | Material compatibility grouping, safety | Exact classification |

### Tier 2: Hydraulic System Properties (filters, pumps, valves)
| Property | Why | Precision Needed |
|---|---|---|
| Bulk modulus | System stiffness, water hammer, control response | ±10%. Often unavailable for commercial blends — use family defaults. |
| Pour point | Cold-start risk, minimum operating temperature | ±5°F. Published on every oil TDS. |
| Flash point / fire point | Safety classification, fire-resistant fluid selection | Exact from TDS. |
| Viscosity index (VI) | Indicates how much viscosity changes with temperature | Integer value from TDS. |
| Air release value | Foaming and cavitation risk | From TDS or ASTM D3427. |
| Water saturation / demulsibility | Water contamination management | Important for condition monitoring. |
| Foaming tendency (ASTM D892) | Reservoir and filter design | From TDS. |

### Tier 3: Spray/Nozzle Properties
| Property | Why | Precision Needed |
|---|---|---|
| Surface tension | Droplet formation, spray pattern, atomization quality | ±5%. Often hard to find for commercial fluids. |
| Vapor pressure vs. temperature | Flash atomization, cavitation | ±10% at operating temperature. |
| Dynamic viscosity | Nozzle flow calculations (some correlations use dynamic, not kinematic) | Derived from kinematic × density. |

### Tier 4: Specialized
| Property | Why | Precision Needed |
|---|---|---|
| Thermal conductivity | Heat exchanger design | ±10%. |
| Specific heat | Cooling system sizing | ±5%. |
| Electrical conductivity | ESD-sensitive applications | Order of magnitude. |
| Refractive index | Online contamination monitoring | Not needed for selection; useful for monitoring. |

### Temperature/Pressure Dependencies

Most properties above are functions of temperature. Pressure effects are negligible for liquids below ~5000 PSI except for:
- **Bulk modulus** — significant pressure dependence; store at reference pressure (atmospheric) and note.
- **Viscosity** — pressure-viscosity coefficient (α) matters for EHL lubrication calculations. Relevant for pumps, not filters or nozzles. Defer.
- **Density** — compressibility is <1% below 5000 PSI. Ignore.

**Recommendation:** Store all properties indexed by temperature. Do not add a pressure dimension to `fluid_properties` — it adds complexity for a negligible effect in the verticals we're building first. Add a `pressure_psi` column later if/when a vertical requires it (e.g., high-pressure pump seals, EHL contacts).

---

## 3. Sourcing Strategy

### Source Hierarchy (by authority, highest first)

| Source | Authority | Coverage | Notes |
|---|---|---|---|
| **NIST WebBook / NIST TDE** | Highest (primary measurement data) | Pure compounds only: water, glycols, esters. NOT commercial oil blends. | Free API available. Excellent for water, glycol, simple solvents. Useless for mineral oil, which is a complex petroleum mixture. |
| **CRC Handbook of Chemistry & Physics** | Very high | Pure compounds, common solutions | Not freely available; data often appears in secondary references. |
| **ASTM / ISO test method standards** | High (defines how to measure) | Defines the property, not the fluid's value | Useful for understanding what a TDS value means (e.g., ASTM D445 = how viscosity is measured). |
| **Vendor Technical Data Sheets (TDS)** | Medium-high | Commercial fluids (oils, greases, synthetics) | **This is the primary source for mineral oils and commercial hydraulic fluids.** Every oil manufacturer publishes TDS. Example: Shell Tellus S2 M 46 TDS gives viscosity at 40°C and 100°C, VI, pour point, flash point, density. |
| **Engineering ToolBox** | Medium | Wide but shallow; citations often unspecified | Good for quick reference; verify against primary sources. Currently used in bootstrap — adequate for initial seeding. |
| **Perry's Chemical Engineers' Handbook** | High for process fluids | Aqueous solutions, acids, bases, solvents | Standard reference for chemical process fluids. |
| **Manufacturer application guides** | Medium | Application-specific | Parker, Donaldson, HYDAC all publish fluid compatibility guides. Already in raw-fetch/. |

### Sourcing Priority by Fluid Frequency

**Phase 1 — Hydraulic Filters + Spray Nozzles (shared fluids)**

These fluids appear in both of the first two verticals:

| Fluid | Filter Relevance | Nozzle Relevance | Priority Source |
|---|---|---|---|
| Water | Cooling loops, washdown systems | Primary spray fluid | NIST (done) |
| Mineral oil ISO 32/46/68 | ~80% of hydraulic systems | Hydraulic spray nozzles | Vendor TDS (Shell Tellus, Mobil DTE, Chevron Rando) |
| Water-glycol (HFC) | Fire-resistant systems | Fire-resistant spray applications | Vendor TDS (Houghton-on-Cool, Quaker) |
| Phosphate ester (HFDR) | Aircraft, steel mills | Specialized | Vendor TDS (Skydrol, Fyrquel) |
| NaOCl / bleach | Water treatment plant filters | Dosing nozzles | Perry's + vendor TDS (done) |
| Diesel / fuel oil | Fuel filtration | Combustion nozzles | Vendor TDS + Engineering ToolBox |
| HWCF / emulsions (HFA/HFB) | Metalworking, mining | Metalworking spray | Vendor TDS |

**Phase 2 — Expand Within Hydraulic Filters**

| Fluid | Why | Source |
|---|---|---|
| Polyol ester (HFDU) | Growing fire-resistant segment, biodegradable | Vendor TDS (Mobil EAL) |
| PAO synthetic | High-performance hydraulic systems | Vendor TDS (Mobil SHC) |
| Automatic transmission fluid (ATF) | Mobile equipment, some industrial | Vendor TDS |
| Turbine oil (ISO 32/46) | Turbine lube + hydraulic systems | Vendor TDS (same base as hydraulic, different additive package) |
| Gear oil (ISO 150-460) | Gearbox filtration | Vendor TDS |
| Contaminated/degraded oil (acids, varnish, water) | Condition monitoring, filter selection for cleanup | Published degradation data + contamination guidelines |

**Phase 3 — Expand for Pump/Valve Verticals**

| Fluid | Why | Source |
|---|---|---|
| Concentrated acids (H₂SO₄, HCl, HNO₃) | Chemical process pumps | NIST + Perry's |
| Caustic solutions (NaOH, KOH) | Chemical process pumps | NIST + Perry's |
| Slurries and suspensions | Slurry pumps, filtration | Empirical data; highly application-specific |
| Cryogenic fluids (LNG, LN₂) | Cryogenic valves and pumps | NIST |
| Food-grade fluids (NSF H1 oils, CIP solutions) | Food/pharma pumps and valves | Vendor TDS + FDA/NSF standards |

---

## 4. Schema Recommendations

### 4.1 Add to `fluids` Table

```sql
ALTER TABLE fluids ADD COLUMN fluid_class TEXT;
-- ISO 6743/4 classification for hydraulic fluids (HH, HL, HM, HV, HG, HFAE, HFAS, HFB, HFC, HFDR, HFDU)
-- ISO 6743/9 for lubricants
-- Provides machine-readable grouping that matters for compatibility and property lookup

ALTER TABLE fluids ADD COLUMN viscosity_grade TEXT;
-- ISO 3448 viscosity grade: "ISO VG 32", "ISO VG 46", etc.
-- NULL for non-oil fluids

ALTER TABLE fluids ADD COLUMN trade_names TEXT;
-- JSON array: ["Shell Tellus S2 M 46", "Mobil DTE 25", "Chevron Rando HDZ 46"]
-- Maps commercial products to their generic fluid identity

ALTER TABLE fluids ADD COLUMN base_stock TEXT;
-- API base stock group: "Group I", "Group II", "Group III", "PAO", "Ester", "PIB"
-- Matters for compatibility and additive response
```

### 4.2 Add to `fluid_properties` Table

```sql
ALTER TABLE fluid_properties ADD COLUMN surface_tension_dyn_cm REAL;
ALTER TABLE fluid_properties ADD COLUMN thermal_conductivity_btu_hr_ft_f REAL;
ALTER TABLE fluid_properties ADD COLUMN pour_point_f REAL;
ALTER TABLE fluid_properties ADD COLUMN flash_point_f REAL;
ALTER TABLE fluid_properties ADD COLUMN viscosity_index INTEGER;
ALTER TABLE fluid_properties ADD COLUMN air_release_min REAL;
ALTER TABLE fluid_properties ADD COLUMN water_saturation_ppm REAL;
ALTER TABLE fluid_properties ADD COLUMN foaming_tendency_ml REAL;
```

**Note on temperature-independent properties:** `pour_point_f`, `flash_point_f`, and `viscosity_index` are single values (not temperature-dependent). Storing them in the property table (which is indexed by temperature) is slightly denormalized. Two options:

- **Option A (simple):** Store these in the property row where `temperature_f` = the reference temperature (e.g., pour point is measured at one temperature, store it there). Accept the denormalization.
- **Option B (clean):** Add a `fluid_static_properties` table for single-value properties.

**Recommendation:** Option B — add a small `fluid_static_properties` table. The `fluid_properties` table stays strictly for temperature-dependent properties, which is conceptually cleaner and avoids confusion.

```sql
CREATE TABLE fluid_static_properties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id            TEXT NOT NULL REFERENCES fluids(id),
    property_key        TEXT NOT NULL,      -- "pour_point_f", "flash_point_f", "viscosity_index", etc.
    value_numeric       REAL,
    value_text          TEXT,
    unit                TEXT,
    source              TEXT,
    confidence          REAL DEFAULT 1.0,
    notes               TEXT,
    UNIQUE(fluid_id, property_key)
);
```

### 4.3 Add Viscosity-Temperature Model Table

```sql
CREATE TABLE fluid_viscosity_models (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id        TEXT NOT NULL REFERENCES fluids(id),
    model_type      TEXT NOT NULL,       -- "walther" (ASTM D341), "andrade", "polynomial"
    -- Walther: log log(ν + 0.7) = A - B·log(T_K)
    -- Andrade: ln(µ) = A + B/T_K
    param_a         REAL NOT NULL,
    param_b         REAL NOT NULL,
    param_c         REAL,                -- for higher-order models
    temp_min_f      REAL,                -- validity range
    temp_max_f      REAL,
    r_squared       REAL,                -- fit quality
    source          TEXT,
    UNIQUE(fluid_id, model_type)
);
```

This is high-value: with Walther coefficients for each hydraulic oil grade, the system can predict viscosity at any operating temperature. Every hydraulic filter consultation needs this — "what's the viscosity at your cold-start temperature?" can be answered from the model instead of requiring the exact temperature to be in the lookup table.

### 4.4 Add Fluid Mixture Table

For future support of blended/diluted fluids:

```sql
CREATE TABLE fluid_mixtures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mixture_id      TEXT NOT NULL,        -- slug for the mixture
    component_fluid_id TEXT NOT NULL REFERENCES fluids(id),
    volume_fraction REAL NOT NULL,        -- 0.0 to 1.0
    UNIQUE(mixture_id, component_fluid_id)
);
```

**Defer this.** The current single-fluid-with-concentration model works for the immediate use cases. Mixture modeling adds complexity and should wait until a real need emerges.

### 4.5 Schema Changes Summary

| Change | Priority | Reason |
|---|---|---|
| Add `fluid_class`, `viscosity_grade`, `trade_names`, `base_stock` to `fluids` | **Sprint 2** | Essential for fluid identification and grouping |
| Add `fluid_static_properties` table | **Sprint 2** | Pour point, flash point, VI — needed for every consultation |
| Add `fluid_viscosity_models` table | **Sprint 2** | Temperature-viscosity interpolation — the most valuable calculation for filter selection |
| Add surface tension, thermal conductivity to `fluid_properties` | **Sprint 3** | Needed when nozzle vertical connects |
| Add `fluid_mixtures` table | **Defer** | No immediate use case |

---

## 5. Build Plan

### Step 1: Schema Migration (Sprint 2, before ingest)
1. Add columns to `fluids` table.
2. Create `fluid_static_properties` table.
3. Create `fluid_viscosity_models` table.
4. Update `bootstrap.py` to populate new fields for the existing 7 fluids.

### Step 2: Populate Existing Fluids (Sprint 2)
For each of the 7 seeded fluids, fill in:
- `fluid_class` and `viscosity_grade` (from ISO standards — known values, no sourcing needed).
- `trade_names` (top 3 commercial equivalents — Shell, Mobil, Chevron for mineral oils).
- Pour point, flash point, viscosity index → `fluid_static_properties` (from vendor TDS — one TDS per oil grade).
- Walther coefficients for mineral oils → `fluid_viscosity_models` (fit from existing 3-4 temperature points, or from published data in Parker/Bosch Rexroth fluid guides).

### Step 3: Add Diesel and Fuel Oils (Sprint 2)
- `diesel-fuel-no2` — Diesel #2 fuel oil. Used in fuel filtration (a common hydraulic filter adjacent application).
- Properties widely available from Engineering ToolBox and fuel TDS.

### Step 4: Expand Mineral Oil Grades (Sprint 3)
- ISO VG 10, 15, 22, 100, 150 — cover the full range of hydraulic oil grades.
- Each needs: viscosity at 40°C and 100°C (from ISO VG definition), density, VI, pour point, flash point.
- Source: vendor TDS or ISO 3448 reference table.

### Step 5: Add Fire-Resistant Fluids (Sprint 3)
- Polyol ester (HFDU): Mobil EAL 46 or equivalent.
- PAG-based (HFAS): if demand appears.
- Enrich existing water-glycol and phosphate ester records with static properties and viscosity models.

### Step 6: Add Process Fluids for Future Verticals (Sprint 4+)
- Acids, caustics, cryogenics — driven by vertical demand.
- Use NIST WebBook API for pure compounds.
- Use Perry's for common solutions.

### Data Entry Method
For Sprint 2 (small number of fluids), populate via:
1. Update `bootstrap.py` with the new seed data inline.
2. Run `python -m pipeline bootstrap` to re-seed.
3. Verify with `python -m pipeline status`.

For Sprint 3+ (larger volumes), build a `fluid_importer.py` that reads a structured YAML or CSV and inserts into the database. This avoids bootstrap.py growing indefinitely.

---

## Appendix: Current State vs. Target

| Aspect | Current (7 fluids) | Target (Sprint 2 complete) |
|---|---|---|
| Fluid count | 7 | 8-9 (add diesel, maybe ATF) |
| Properties per fluid | 2-5 temp points, viscosity + density only | 3-5 temp points + static properties (VI, pour, flash) |
| Viscosity models | None | Walther coefficients for all oil grades |
| Trade name mapping | None | Top 3 commercial equivalents per grade |
| ISO classification | None | ISO 6743/4 class for all hydraulic fluids |
| Material compatibility | 24 records (3 fluids) | 40-50 records (cover all 8-9 fluids × key materials) |
| Sourcing provenance | Partial (`source` column exists) | Every value has a source string |

The 7 existing fluids cover ~90% of hydraulic filter consultations. The gap isn't quantity — it's depth. Making each record complete (static properties, viscosity model, trade names, classification) is more valuable than adding more fluids.
