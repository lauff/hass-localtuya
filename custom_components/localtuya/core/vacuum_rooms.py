"""Room (segment) cleaning frames for Tuya vacuums.

Raw DPs are sent and reported as base64 strings. The frames below were
captured from the Lefant app (Lefant M5):

    aa 00 LEN payload CHK            layout A, LEN = 1 byte
    aa 00 TYPE LEN16 payload CHK     layout B, LEN16 = 2 bytes big endian
    CHK = sum of the payload bytes modulo 256

Room clean (written by the app):  layout A, payload 14 01 COUNT ID...
Room list (reported by the vacuum): layout B, payload VERSION COUNT, then per
room: ID, 6 setting bytes, name length (u16 big endian), name (utf-8).
"""

from __future__ import annotations

import base64
import binascii

ROOM_CLEAN_COMMAND = 0x14


def build_frame(payload: bytes) -> bytes:
    """Wrap payload in a layout A frame."""
    if len(payload) > 255:
        raise ValueError("Payload too long")
    return b"\xaa\x00" + bytes([len(payload)]) + payload + bytes([sum(payload) & 0xFF])


def parse_frame(raw: bytes) -> bytes | None:
    """Return the payload of a layout A or B frame, None if it is not valid."""
    if len(raw) < 4 or raw[:2] != b"\xaa\x00":
        return None
    candidates = []
    if len(raw) == raw[2] + 4:
        candidates.append(raw[3:-1])
    if len(raw) >= 6 and len(raw) == int.from_bytes(raw[3:5], "big") + 6:
        candidates.append(raw[5:-1])
    for payload in candidates:
        if sum(payload) & 0xFF == raw[-1]:
            return payload
    return None


def encode_room_clean(room_ids: list[int]) -> str:
    """Return the base64 room clean frame for the rooms, in cleaning order."""
    if not room_ids:
        raise ValueError("No rooms given")
    if any(not 0 <= room_id <= 255 for room_id in room_ids):
        raise ValueError(f"Room ids must be 0..255: {room_ids}")
    payload = bytes([ROOM_CLEAN_COMMAND, 1, len(room_ids), *room_ids])
    return base64.b64encode(build_frame(payload)).decode()


def decode_room_list(value) -> dict[int, str] | None:
    """Return {room id: name} from a base64 room list frame, None if invalid."""
    if not isinstance(value, str):
        return None
    try:
        payload = parse_frame(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError):
        return None
    if payload is None or len(payload) < 2:
        return None

    rooms, pos = {}, 2
    for _ in range(payload[1]):
        if pos + 9 > len(payload):
            return None
        room_id = payload[pos]
        name_len = int.from_bytes(payload[pos + 7 : pos + 9], "big")
        pos += 9
        if pos + name_len > len(payload):
            return None
        rooms[room_id] = payload[pos : pos + name_len].decode("utf-8", "replace")
        pos += name_len
    return rooms if pos == len(payload) else None


def parse_rooms_config(text: str | None) -> dict[int, str]:
    """Parse "11:Hall, 7:Floor" into {11: "Hall", 7: "Floor"}."""
    rooms = {}
    for item in (text or "").split(","):
        if not item.strip():
            continue
        room_id, _, name = item.partition(":")
        room_id = int(room_id.strip())
        rooms[room_id] = name.strip() or f"Room {room_id}"
    return rooms
