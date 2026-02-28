"""
Spray Nozzles — Application Domain Taxonomy

Each domain defines:
  - id: slug used in consultation_sessions.application_domain
  - name: human-readable label
  - description: one-line explanation
  - diagnostic_priorities: ordered list of what to ask about first
"""
from __future__ import annotations

APPLICATION_DOMAINS = [
    {
        "id": "tank_cleaning",
        "name": "Tank Cleaning",
        "description": "CIP, tank washing, vessel cleaning",
        "diagnostic_priorities": [
            "vessel geometry (diameter, orientation, internal obstructions)",
            "cleaning agent and concentration",
            "temperature",
            "required cycle time",
            "fitting type (sanitary, threaded, flanged)",
            "current cleaning method and what's failing",
        ],
    },
    {
        "id": "spray_drying",
        "name": "Spray Drying",
        "description": "Powder production, encapsulation, dairy/pharma drying",
        "diagnostic_priorities": [
            "feed properties (solids content, viscosity, heat sensitivity)",
            "inlet/outlet temperatures",
            "target particle size and morphology",
            "production rate",
            "atomizer type preference (rotary, pressure, two-fluid)",
            "existing chamber dimensions if retrofit",
        ],
    },
    {
        "id": "coating",
        "name": "Coating",
        "description": "Surface coating, painting, film application",
        "diagnostic_priorities": [
            "substrate and line speed",
            "coating material properties (viscosity, solids, solvent)",
            "target film thickness and uniformity tolerance",
            "spray distance",
            "pattern width needed",
            "surface preparation",
        ],
    },
    {
        "id": "gas_cooling",
        "name": "Gas Cooling",
        "description": "Quench towers, gas conditioning, evaporative cooling",
        "diagnostic_priorities": [
            "gas composition and inlet temperature",
            "target outlet temperature",
            "available water pressure and quality",
            "tower diameter and gas velocity",
            "evaporation efficiency requirements",
            "drift/carryover concerns",
        ],
    },
    {
        "id": "humidification",
        "name": "Humidification",
        "description": "Air humidity control, textile, printing, storage",
        "diagnostic_priorities": [
            "space dimensions and airflow",
            "target humidity range",
            "water quality",
            "droplet size constraints (avoid wetting)",
            "control requirements",
        ],
    },
    {
        "id": "dust_suppression",
        "name": "Dust Suppression",
        "description": "Mining, material handling, demolition",
        "diagnostic_priorities": [
            "dust source and particle size",
            "area coverage needed",
            "water availability",
            "wind conditions",
            "chemical additives",
        ],
    },
    {
        "id": "fire_protection",
        "name": "Fire Protection",
        "description": "Deluge systems, water mist",
        "diagnostic_priorities": [
            "hazard classification",
            "required application rate",
            "ceiling height",
            "nozzle spacing",
            "water supply pressure and flow",
        ],
    },
    {
        "id": "chemical_injection",
        "name": "Chemical Injection",
        "description": "Dosing, mixing, reactor injection",
        "diagnostic_priorities": [
            "injection point conditions (pressure, temperature, flow)",
            "chemical properties",
            "mixing requirements",
            "materials compatibility",
        ],
    },
    {
        "id": "agricultural",
        "name": "Agricultural",
        "description": "Crop spraying, pest control, fertilizer application",
        "diagnostic_priorities": [
            "crop type and canopy density",
            "target pest/disease",
            "application rate",
            "boom height and speed",
            "drift constraints",
        ],
    },
    {
        "id": "descaling",
        "name": "Descaling",
        "description": "Steel mill, metalworking",
        "diagnostic_priorities": [
            "steel temperature and grade",
            "scale thickness",
            "standoff distance",
            "available pressure",
            "nozzle header configuration",
        ],
    },
    {
        "id": "general",
        "name": "General",
        "description": "Doesn't fit above or unclear",
        "diagnostic_priorities": [],
    },
]


def get_domain(domain_id: str) -> dict | None:
    """Get a specific domain by ID."""
    for d in APPLICATION_DOMAINS:
        if d["id"] == domain_id:
            return d
    return None


def format_domains_for_prompt() -> str:
    """Format all domains for inclusion in a system prompt."""
    lines = []
    for d in APPLICATION_DOMAINS:
        lines.append(f"- {d['id']}: {d['description']}")
    return "\n".join(lines)
