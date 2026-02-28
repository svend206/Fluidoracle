"""
Fluid Power Systems (FPS) — Platform Configuration

FPS serves engineers working on closed-loop hydraulic and pneumatic circuits:
excavators, presses, injection molding, mobile equipment. These engineers think
in system terms — changing one component affects others.
"""
from __future__ import annotations

PLATFORM_ID = "fps"
DISPLAY_NAME = "Fluid Power Systems"
DESCRIPTION = (
    "AI consulting for closed-loop hydraulic and pneumatic systems — "
    "filtration, pumps, valves, seals, hoses, and actuators."
)

# Registered verticals (vertical_id → module path)
VERTICALS = {
    "hydraulic_filtration": "platforms.fps.verticals.hydraulic_filtration",
}
