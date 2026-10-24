"""Tests for the vacuum room frames (captured from a Lefant M5)."""

import base64

import pytest

from custom_components.localtuya.core.vacuum_rooms import (
    decode_room_list,
    encode_room_clean,
    parse_rooms_config,
)

# Room list as reported by the vacuum (layout B frame)
ROOM_LIST = base64.b64encode(
    bytes.fromhex(
        "aa0001005f01060500020301010f000957432048657272656e0600020301010f0009574320"
        "46726175656e0700020301010f0004466c75720900020301010f0005426f6f74680a000203"
        "01010f000745696e67616e670b01020001010f000548616c6c654d"
    )
).decode()

ROOMS = {
    5: "WC Herren",
    6: "WC Frauen",
    7: "Flur",
    9: "Booth",
    10: "Eingang",
    11: "Halle",
}


def b64(hex_frame: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_frame)).decode()


def test_encode_room_clean():
    # frames the app sent
    assert encode_room_clean([11]) == b64("aa00041401010b21")
    assert encode_room_clean([7]) == b64("aa0004140101071d")
    assert encode_room_clean([11, 7]) == b64("aa00051401020b0729")


def test_encode_room_clean_invalid():
    with pytest.raises(ValueError):
        encode_room_clean([])
    with pytest.raises(ValueError):
        encode_room_clean([256])


def test_decode_room_list():
    assert decode_room_list(ROOM_LIST) == ROOMS


def test_decode_room_list_invalid():
    assert decode_room_list(None) is None
    assert decode_room_list("not base64!") is None
    assert decode_room_list(b64("aa00041401010b22")) is None  # bad checksum
    assert decode_room_list(ROOM_LIST[:-8] + "AAAAAAAA") is None


def test_parse_rooms_config():
    assert parse_rooms_config("11:Halle, 7 : Flur,5") == {
        11: "Halle",
        7: "Flur",
        5: "Room 5",
    }
    assert parse_rooms_config("") == {}
    assert parse_rooms_config(None) == {}
    with pytest.raises(ValueError):
        parse_rooms_config("Halle:11")
