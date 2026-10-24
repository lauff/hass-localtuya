"""Test for localtuya."""

from copy import deepcopy
from unittest.mock import AsyncMock, call

import pytest
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError

from . import *
from .test_vacuum_rooms import ROOM_LIST, ROOMS, b64
from custom_components.localtuya.vacuum import (
    LocalTuyaVacuum,
    DOMAIN as PLATFORM_DOMAIN,
    VacuumActivity,
    VacuumEntityFeature,
    CONF_MODE_DP,
    CONF_PAUSE_DP,
    CONF_RETURN_HOME_DP,
    FEATURE_CLEAN_AREA,
    Segment,
)

CONFIG = {
    DEVICE_NAME: {
        **DEVICE_CONFIG,
        "entities": [
            {
                "entity_category": "None",
                "powergo_dp": "2",
                "idle_status_value": "standby,sleep",
                "docked_status_value": "charging,chargecompleted,charge_done",
                "returning_status_value": "docking,to_charge,goto_charge",
                "paused_state": "paused",
                "stop_status": "standby",
                "pause_dp": "101",
                "mode_dp": "3",
                "modes": "smart,zone,pose,part,chargego,wallfollow,selectroom",
                "return_mode": "chargego",
                "fan_speed_dp": "14",
                "fan_speeds": "strong,normal,quiet",
                "clean_time_dp": "17",
                "clean_area_dp": "16",
                "clean_record_dp": "19",
                "locate_dp": "13",
                "fault_dp": "18",
                "friendly_name": "",
                "id": "5",
                "platform": PLATFORM_DOMAIN,
                "icon": "mdi:robot-vacuum",
            }
        ],
    }
}

DPS_STATUS = {
    "2": True,  # powergo_dp
    "3": "smart",  # mode_dp
    "5": "cleaning",  # id - state
    "13": False,  # locate_dp
    "14": "quiet",  # fan_speed_dp
    "16": 0,  # clean_area_dp
    "17": 0,  # clean_time_dp
    "18": 0,  # fault_dp
    "19": "",  # clean_record_dp
    "101": False,  # pause_dp
}


async def test_vacuum():
    device = await init(CONFIG, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entities: list[LocalTuyaVacuum] = get_entites(device)

    assert len(entities) > 0
    entity_1, *_ = entities
    assert type(entity_1) is LocalTuyaVacuum

    entity_1_cfg = CONFIG[DEVICE_NAME]["entities"][0]

    status = DPS_STATUS.copy()
    device.status_updated(status)
    assert entity_1.state == VacuumActivity.CLEANING
    assert entity_1.fan_speed == "quiet"
    assert status[entity_1_cfg[CONF_MODE_DP]] in entity_1._modes_list

    device.status_updated({entity_1_cfg[CONF_PAUSE_DP]: True})
    assert entity_1.state == VacuumActivity.PAUSED

    device.status_updated({entity_1_cfg["id"]: "standby"})
    assert entity_1.state == VacuumActivity.IDLE


async def test_vacuum_send_command_without_params():
    """send_command("set_mode") without params must not raise."""
    device = await init(CONFIG, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)
    device.set_dp = AsyncMock()

    await entity_1.async_send_command("set_mode")
    device.set_dp.assert_not_awaited()


async def test_vacuum_return_home():
    """Without return_home_dp, returning home writes return_mode to the mode DP."""
    device = await init(CONFIG, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)
    entity_1_cfg = CONFIG[DEVICE_NAME]["entities"][0]
    device.set_dp = AsyncMock()

    assert entity_1.supported_features & VacuumEntityFeature.RETURN_HOME
    await entity_1.async_return_to_base()
    device.set_dp.assert_awaited_once_with("chargego", entity_1_cfg[CONF_MODE_DP])


async def test_vacuum_return_home_dp():
    """With return_home_dp, returning home writes True to that DP."""
    config = deepcopy(CONFIG)
    entity_cfg = config[DEVICE_NAME]["entities"][0]
    entity_cfg[CONF_RETURN_HOME_DP] = "20"
    entity_cfg["modes"] = "smart,zone"  # return_mode is not a mode on such devices

    device = await init(config, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)
    device.set_dp = AsyncMock()

    assert entity_1.supported_features & VacuumEntityFeature.RETURN_HOME
    await entity_1.async_return_to_base()
    device.set_dp.assert_awaited_once_with(True, "20")


def rooms_config():
    """Vacuum config with room cleaning (DP numbers of a Lefant M5)."""
    config = deepcopy(CONFIG)
    config[DEVICE_NAME]["entities"][0].update(
        {"room_clean_dp": "113", "rooms_dp": "183", "rooms": "11:Hall"}
    )
    return config


async def test_vacuum_rooms_from_dp():
    device = await init(rooms_config(), PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)

    device.status_updated({**DPS_STATUS, "183": ROOM_LIST})
    # rooms reported by the vacuum, the configured name wins
    assert entity_1.rooms == {**ROOMS, 11: "Hall"}
    assert entity_1.extra_state_attributes["rooms"]["7"] == "Flur"

    assert entity_1.supported_features & VacuumEntityFeature.SEND_COMMAND
    if FEATURE_CLEAN_AREA:
        assert entity_1.supported_features & FEATURE_CLEAN_AREA
    if Segment:
        segments = await entity_1.async_get_segments()
        assert Segment(id="11", name="Hall") in segments
        assert len(segments) == len(ROOMS)


async def test_vacuum_clean_rooms():
    device = await init(rooms_config(), PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)
    device.status_updated({**DPS_STATUS, "183": ROOM_LIST})
    device.set_dp = AsyncMock()

    # by name (case insensitive) and id, in cleaning order
    await entity_1.async_send_command("clean_rooms", {"rooms": ["hall", 7]})
    assert device.set_dp.await_args_list == [
        call(False, "2"),  # powergo_dp
        call(b64("aa00051401020b0729"), "113"),  # room frame
        call("CleanModeSectorbased", "3"),  # mode_dp
    ]

    device.set_dp.reset_mock()
    await entity_1.async_clean_segments(["11"])
    assert device.set_dp.await_args_list[1] == call(b64("aa00041401010b21"), "113")

    with pytest.raises(HomeAssistantError):
        await entity_1.async_send_command("clean_rooms", {"rooms": ["Kitchen"]})
    with pytest.raises(HomeAssistantError):
        await entity_1.async_send_command("clean_rooms")


async def test_vacuum_clean_rooms_not_configured():
    device = await init(CONFIG, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)
    device.set_dp = AsyncMock()

    if FEATURE_CLEAN_AREA:
        assert not entity_1.supported_features & FEATURE_CLEAN_AREA
    with pytest.raises(HomeAssistantError):
        await entity_1.async_clean_rooms([11])
    device.set_dp.assert_not_awaited()


async def test_vacuum_base_station():
    config = deepcopy(CONFIG)
    config[DEVICE_NAME]["entities"][0]["base_station_dp"] = "158"
    device = await init(config, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)

    device.status_updated({**DPS_STATUS, "158": b64("aa00070102000000000003")})
    attrs = entity_1.extra_state_attributes
    assert attrs["fresh_water_tank"] == "empty"
    assert attrs["waste_water_tank"] == "ok"
    assert attrs["base_station_busy"] is False

    # an invalid frame keeps the last known values
    device.status_updated({"158": "garbage"})
    assert entity_1.extra_state_attributes["fresh_water_tank"] == "empty"


async def test_vacuum_base_station_restored():
    config = deepcopy(CONFIG)
    config[DEVICE_NAME]["entities"][0]["base_station_dp"] = "158"
    device = await init(config, PLATFORM_DOMAIN, LocalTuyaVacuum)
    entity_1, *_ = get_entites(device)

    entity_1.status_restored(
        State(
            "vacuum.test",
            "docked",
            {"fresh_water_tank": "ok", "waste_water_tank": "removed", "rooms": "bad"},
        )
    )
    assert entity_1.extra_state_attributes["waste_water_tank"] == "removed"
