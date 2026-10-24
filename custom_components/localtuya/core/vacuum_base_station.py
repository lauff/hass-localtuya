"""Base station status frame of Tuya vacuums with a wash / empty station.

Seen on a Lefant M5 (DP 158, "base station real-time status"). Layout A frame
(see vacuum_rooms.py), 7 payload bytes:

    b0  always 01
    b1  fresh water tank: 0 ok, 1 removed, 2 empty
    b2  waste water tank: 0 ok, 1 removed, 2 full (assumed, by analogy with b1)
    b3..b5  unknown, always 0 so far
    b6  1 while the station works (dust collection, mop wash, drying)

The vacuum only reports the station while it is docked.
"""

from __future__ import annotations

import base64
import binascii

from .vacuum_rooms import parse_frame

FRESH_WATER_TANK = "fresh_water_tank"
WASTE_WATER_TANK = "waste_water_tank"
BASE_STATION_BUSY = "base_station_busy"

FRESH_WATER_STATES = {0: "ok", 1: "removed", 2: "empty"}
WASTE_WATER_STATES = {0: "ok", 1: "removed", 2: "full"}


def decode_base_station(value) -> dict | None:
    """Return the base station attributes from a base64 frame, None if invalid."""
    if not isinstance(value, str):
        return None
    try:
        payload = parse_frame(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError):
        return None
    if payload is None or len(payload) < 7:
        return None

    return {
        FRESH_WATER_TANK: FRESH_WATER_STATES.get(payload[1], f"unknown_{payload[1]}"),
        WASTE_WATER_TANK: WASTE_WATER_STATES.get(payload[2], f"unknown_{payload[2]}"),
        BASE_STATION_BUSY: bool(payload[6]),
    }
