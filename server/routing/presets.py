"""Routing presets: preset name → (profile, costing_options).

Each entry maps to a Valhalla /route request shape:
    costing = <profile>          ('bicycle' | 'pedestrian' | 'auto')
    costing_options.<profile> = <costing_options dict>

The UI lists these in order and sends the selected preset name to the
server; the server resolves it here and merges the dict into the
Valhalla request body. 'custom' is the opt-out — the client ships its
own costing_options and the preset contributes nothing.

'hybrid' is a legacy alias for 'road' — see plan Decision D1.
"""

# Tunable knobs — see Valhalla /route reference. Values chosen to reflect
# the spec's intended user personas. Adjust here, not in the UI.
_PRESETS = {
    "road": {
        "profile": "bicycle",
        "costing_options": {
            "bicycle_type": "Road",
            "use_roads": 0.9,
            "use_hills": 0.4,
            "avoid_bad_surfaces": 0.9,
        },
        "description": "Sealed roads, moderate hills tolerated.",
    },
    "gravel-mtb": {
        "profile": "bicycle",
        "costing_options": {
            "bicycle_type": "Mountain",
            "use_roads": 0.3,
            "use_hills": 0.6,
            "avoid_bad_surfaces": 0.2,
        },
        "description": "Unpaved tracks welcome, hills OK.",
    },
    "easy": {
        "profile": "bicycle",
        "costing_options": {
            "bicycle_type": "Hybrid",
            "use_roads": 0.6,
            "use_hills": 0.1,
            "avoid_bad_surfaces": 0.7,
        },
        "description": "Flat, sealed preferred.",
    },
    "hike": {
        "profile": "pedestrian",
        "costing_options": {
            "use_tracks": 0.9,
            "use_hills": 0.6,
        },
        "description": "On-foot, tracks and paths preferred.",
    },
    "drive": {
        "profile": "auto",
        "costing_options": {},
        "description": "Motor vehicle, shortest time.",
    },
    "custom": {
        "profile": "bicycle",
        "costing_options": {},
        "description": "Bring your own costing options.",
    },
}

# D1: 'hybrid' is a read-side alias for 'road'. Kept because the CHECK
# constraint in route_options accepts it and existing rows may carry it.
_ALIAS = {"hybrid": "road"}


def list_presets():
    """Return the user-facing preset list (hybrid alias excluded)."""
    return [
        {"name": name, "profile": p["profile"], "description": p["description"]}
        for name, p in _PRESETS.items()
    ]


def resolve(name):
    """Resolve a preset name (or legacy alias) to its profile + costing options."""
    resolved = _ALIAS.get(name, name)
    if resolved not in _PRESETS:
        raise ValueError(f"unknown preset: {name}")
    entry = _PRESETS[resolved]
    return {
        "profile": entry["profile"],
        "costing_options": dict(entry["costing_options"]),
    }
