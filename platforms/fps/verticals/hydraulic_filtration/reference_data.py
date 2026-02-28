"""
Hydraulic Filtration — Core Reference Data

Structured reference tables for programmatic use.
The full prose reference data lives in answering_prompt.md and is injected
into the LLM system prompt. This module provides machine-readable versions
for calculations, validation, and UI display.

Sources: ISO 16889:2022, ISO 4406:2021, Donaldson DHP Cat 5.6,
Schroeder L-4139, Eaton Filtration 200, Parker FDCB805UK, Velcon VEL1948.
"""
from __future__ import annotations


# Beta ratio → efficiency mapping (ISO 16889)
BETA_EFFICIENCY = {
    2: 50.0,
    10: 90.0,
    75: 98.7,
    100: 99.0,
    200: 99.5,
    1000: 99.9,
    2000: 99.95,
    4000: 99.97,
}


# ISO 4406 code → particle count range (cumulative particles per mL)
ISO_4406_CODES = {
    28: (1_300_000, 2_500_000),
    27: (640_000, 1_300_000),
    26: (320_000, 640_000),
    25: (160_000, 320_000),
    24: (80_000, 160_000),
    23: (40_000, 80_000),
    22: (20_000, 40_000),
    21: (10_000, 20_000),
    20: (5_000, 10_000),
    19: (2_500, 5_000),
    18: (1_300, 2_500),
    17: (640, 1_300),
    16: (320, 640),
    15: (160, 320),
    14: (80, 160),
    13: (40, 80),
    12: (20, 40),
    11: (10, 20),
    10: (5.0, 10),
    9: (2.5, 5.0),
    8: (1.3, 2.5),
    7: (0.64, 1.3),
    6: (0.32, 0.64),
}


# Target cleanliness by component type (source: Schroeder L-4139)
# Format: ISO 4406 code as "XX/YY/ZZ"
TARGET_CLEANLINESS_BY_COMPONENT = {
    "servo_valve": "15/13/11",
    "proportional_valve": "16/14/12",
    "variable_piston_pump": "16/14/12",
    "fixed_piston_pump": "17/15/12",
    "variable_vane_pump": "17/15/12",
    "fixed_vane_pump": "18/16/13",
    "fixed_gear_pump": "18/16/13",
    "ball_bearing": "15/13/11",
    "roller_bearing": "16/14/12",
    "journal_bearing_high_rpm": "17/15/13",
    "journal_bearing_low_rpm": "18/16/14",
    "gearbox": "18/16/13",
    "hydrostatic_transmission": "16/14/11",
}


# Pressure-stratified cleanliness targets (source: Velcon VEL1948 / Noria)
# {component: {pressure_range: iso_code}}
TARGET_CLEANLINESS_BY_PRESSURE = {
    "servo_valve": {
        "<1500psi": "16/14/12",
        "1500-2500psi": "15/13/11",
        ">2500psi": "14/12/10",
    },
    "proportional_valve": {
        "<1500psi": "17/15/12",
        "1500-2500psi": "16/14/12",
        ">2500psi": "15/13/11",
    },
    "variable_volume_pump": {
        "<1500psi": "17/16/13",
        "1500-2500psi": "17/15/12",
        ">2500psi": "16/14/13",
    },
    "vane_pump": {
        "<1500psi": "19/17/17",
        "1500-2500psi": "18/16/14",
        ">2500psi": "17/16/13",
    },
    "gear_pump": {
        "<1500psi": "19/17/14",
        "1500-2500psi": "18/16/14",
        ">2500psi": "18/16/14",
    },
}


# Component critical clearances in µm (source: Schroeder L-4139)
COMPONENT_CLEARANCES_UM = {
    "gear_pump": (0.5, 5.0),
    "vane_pump": (0.5, 5.0),
    "piston_pump": (0.5, 1.0),
    "control_valve": (1.0, 25.0),
    "servo_valve": (1.0, 4.0),
}


# Bypass valve settings by filter location (bar)
BYPASS_SETTINGS = {
    "return_line": (3.0, 6.0),
    "pressure_line": (10.0, 21.0),
    "suction": (0.2, 0.5),  # vacuum, bar
}


# ISO VG mineral oil viscosity-temperature reference (approximate, cSt)
VISCOSITY_TEMPERATURE = {
    "VG32": {-20: 3000, 0: 400, 20: 80, 40: 32, 60: 15, 80: 8, 100: 4.5},
    "VG46": {-20: 3000, 0: 400, 20: 100, 40: 46, 60: 20, 80: 10, 100: 5.5},
    "VG68": {-20: 5000, 0: 600, 20: 150, 40: 68, 60: 28, 80: 14, 100: 7.5},
    "VG100": {-20: 8000, 0: 900, 20: 230, 40: 100, 60: 40, 80: 20, 100: 11},
}


# New oil typical cleanliness (source: Schroeder L-4139)
NEW_OIL_CLEANLINESS = {
    "mini_container": "17/15/13",
    "barrel": "23/21/18",
    "tanker": "20/18/15",
}
