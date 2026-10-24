"""Tests for the vacuum base station frame (captured from a Lefant M5, DP 158)."""

from custom_components.localtuya.core.vacuum_base_station import decode_base_station

from .test_vacuum_rooms import b64


def station(fresh, waste, busy):
    return {
        "fresh_water_tank": fresh,
        "waste_water_tank": waste,
        "base_station_busy": busy,
    }


def test_decode_base_station():
    # fresh water empty, at the app's "fresh water empty" alert
    assert decode_base_station(b64("aa00070102000000000003")) == station(
        "empty", "ok", False
    )
    # both tanks removed while the station was busy
    assert decode_base_station(b64("aa00070101010000000104")) == station(
        "removed", "removed", True
    )
    assert decode_base_station(b64("aa00070100010000000103")) == station(
        "ok", "removed", True
    )
    assert decode_base_station(b64("aa00070100000000000001")) == station(
        "ok", "ok", False
    )
    # assumed: waste water full = 2, by analogy with fresh water empty
    assert decode_base_station(b64("aa00070100020000000003")) == station(
        "ok", "full", False
    )
    assert decode_base_station(b64("aa00070107000000000008")) == station(
        "unknown_7", "ok", False
    )


def test_decode_base_station_invalid():
    assert decode_base_station(None) is None
    assert decode_base_station("not base64!") is None
    assert decode_base_station(b64("aa00070102000000000004")) is None  # checksum
    assert decode_base_station(b64("aa0002010102")) is None  # too short
