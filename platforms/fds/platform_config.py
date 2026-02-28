"""
Fluid Delivery Systems (FDS) — Platform Configuration

FDS serves engineers working on open-loop fluid delivery processes:
spray coating, agricultural application, cleaning, cooling, humidification.
These engineers think in process terms — optimizing an output.
"""
from __future__ import annotations

PLATFORM_ID = "fds"
DISPLAY_NAME = "Fluid Delivery Systems"
DESCRIPTION = (
    "AI consulting for open-loop fluid delivery processes — "
    "spray nozzles, atomizers, precision applicators."
)

# Registered verticals (vertical_id → module path)
VERTICALS = {
    "spray_nozzles": "platforms.fds.verticals.spray_nozzles",
}
