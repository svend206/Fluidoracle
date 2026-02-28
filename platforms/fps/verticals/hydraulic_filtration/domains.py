"""
Hydraulic Filtration — Application Domain Taxonomy

Each domain defines:
  - id: slug used in consultation_sessions.application_domain
  - name: human-readable label
  - description: one-line explanation
  - diagnostic_priorities: ordered list of what to ask about first
"""
from __future__ import annotations

APPLICATION_DOMAINS = [
    {
        "id": "filter_selection",
        "name": "Filter Selection",
        "description": "Choosing a new filter for a hydraulic or lubrication system",
        "diagnostic_priorities": [
            "current system cleanliness vs. target",
            "component sensitivity (servo valves? piston pumps?)",
            "flow rate",
            "operating pressure",
            "space constraints",
            "element change interval expectation",
            "unusual fluid conditions (high water content, abrasive particles)",
        ],
    },
    {
        "id": "contamination_problem",
        "name": "Contamination Problem",
        "description": "Existing system has cleanliness issues or component failures",
        "diagnostic_priorities": [
            "symptoms (component failures, sticky valves, accelerated wear?)",
            "current ISO code vs. target",
            "oil sample data if available",
            "filter bypass history",
            "ingression sources (cylinder rod seals, reservoir breather, new oil addition)",
        ],
    },
    {
        "id": "system_design",
        "name": "System Design",
        "description": "Designing filtration for a new machine or system",
        "diagnostic_priorities": [
            "circuit diagram/description",
            "pump and valve types and their cleanliness requirements",
            "flow rate",
            "system pressure",
            "fluid type and temperature range",
            "environment (indoor/outdoor/mobile)",
            "maintenance access constraints",
        ],
    },
    {
        "id": "kidney_loop",
        "name": "Kidney Loop / Offline Filtration",
        "description": "Adding or sizing an offline filtration loop",
        "diagnostic_priorities": [
            "reservoir volume",
            "current and target cleanliness levels",
            "primary system flow rate",
            "available power for pump drive",
            "space for separate filter unit",
            "24/7 vs. intermittent operation",
        ],
    },
    {
        "id": "cold_start",
        "name": "Cold Start",
        "description": "Cold start or high-viscosity related filtration issues",
        "diagnostic_priorities": [
            "minimum ambient/fluid temperature",
            "fluid viscosity at cold conditions (or fluid type and grade)",
            "current element collapse pressure rating",
            "bypass valve setting",
            "startup sequence",
        ],
    },
    {
        "id": "condition_monitoring",
        "name": "Condition Monitoring",
        "description": "Setting up oil analysis or ΔP monitoring programs",
        "diagnostic_priorities": [
            "number of systems to monitor",
            "criticality of components",
            "current sampling interval",
            "existing oil analysis data",
            "desire for online vs. offline monitoring",
        ],
    },
    {
        "id": "fluid_change",
        "name": "Fluid Change",
        "description": "Changing fluid type and impact on existing filtration",
        "diagnostic_priorities": [
            "current fluid type",
            "proposed new fluid type",
            "reason for change (fire resistance? biodegradable? OEM requirement?)",
            "current filter element media type",
            "seal materials in system",
        ],
    },
    {
        "id": "mobile_equipment",
        "name": "Mobile Equipment",
        "description": "Hydraulic filtration for mobile/off-highway equipment",
        "diagnostic_priorities": [
            "equipment type (excavator, crane, loader?)",
            "operating environment (dusty? muddy? extreme temperature?)",
            "OEM cleanliness specification",
            "vibration considerations",
            "service interval requirements",
        ],
    },
    {
        "id": "lubrication_system",
        "name": "Lubrication System",
        "description": "Gearbox, bearing, or lube system filtration",
        "diagnostic_priorities": [
            "equipment type (gearbox, bearing housing)",
            "oil type and viscosity",
            "operating temperature range",
            "target ISO code",
            "continuous vs. batch lubrication",
        ],
    },
    {
        "id": "fuel_system",
        "name": "Fuel System",
        "description": "Diesel or hydraulic fuel filtration",
        "diagnostic_priorities": [
            "fuel type (diesel, biodiesel, hydraulic)",
            "contamination concerns (water, microbial, particles)",
            "storage or in-system filtration",
            "flow rate and pressure",
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
