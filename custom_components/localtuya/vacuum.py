"""Platform to locally control Tuya-based vacuum devices."""

import asyncio
import logging
from functools import partial
from .config_flow import col_to_select

import voluptuous as vol
from homeassistant.components.vacuum import (
    DOMAIN,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError

try:  # Home Assistant >= 2026.3
    from homeassistant.components.vacuum import Segment
except ImportError:
    Segment = None

from .core.vacuum_rooms import (
    decode_room_list,
    encode_room_clean,
    parse_rooms_config,
)
from .entity import LocalTuyaEntity, async_setup_entry
from .const import (
    CONF_CLEAN_AREA_DP,
    CONF_CLEAN_RECORD_DP,
    CONF_CLEAN_TIME_DP,
    CONF_DOCKED_STATUS_VALUE,
    CONF_FAN_SPEED_DP,
    CONF_FAN_SPEEDS,
    CONF_FAULT_DP,
    CONF_IDLE_STATUS_VALUE,
    CONF_LOCATE_DP,
    CONF_MODE_DP,
    CONF_MODES,
    CONF_PAUSED_STATE,
    CONF_POWERGO_DP,
    CONF_RETURN_MODE,
    CONF_RETURNING_STATUS_VALUE,
    CONF_STOP_STATUS,
    CONF_PAUSE_DP,
    CONF_RETURN_HOME_DP,
    CONF_ROOM_CLEAN_DP,
    CONF_ROOM_CLEAN_MODE,
    CONF_ROOMS_DP,
    CONF_ROOMS,
)

_LOGGER = logging.getLogger(__name__)

CLEAN_TIME = "clean_time"
CLEAN_AREA = "clean_area"
CLEAN_RECORD = "clean_record"
MODES_LIST = "cleaning_mode_list"
MODE = "cleaning_mode"
FAULT = "fault"
ROOMS = "rooms"

# VacuumEntityFeature.CLEAN_AREA exists since Home Assistant 2026.3
FEATURE_CLEAN_AREA = getattr(VacuumEntityFeature, "CLEAN_AREA", None)
COMMAND_CLEAN_ROOMS = "clean_rooms"
# Delay between the writes of a room clean, the Lefant app uses ~100 ms.
ROOM_CLEAN_WRITE_DELAY = 0.1

DEFAULT_IDLE_STATUS = "standby,sleep"
DEFAULT_RETURNING_STATUS = "docking,to_charge,goto_charge"
DEFAULT_DOCKED_STATUS = "charging,chargecompleted,charge_done,charging_dock"
DEFAULT_MODES = "smart,wall_follow,spiral,single"
DEFAULT_FAN_SPEEDS = "low,normal,high"
DEFAULT_PAUSED_STATE = "paused"
DEFAULT_RETURN_MODE = "chargego"
DEFAULT_STOP_STATUS = "standby"
DEFAULT_ROOM_CLEAN_MODE = "CleanModeSectorbased"


def flow_schema(dps):
    """Return schema used in config flow."""
    return {
        vol.Required(CONF_POWERGO_DP): col_to_select(dps, is_dps=True),
        vol.Required(CONF_IDLE_STATUS_VALUE, default=DEFAULT_IDLE_STATUS): str,
        vol.Required(CONF_DOCKED_STATUS_VALUE, default=DEFAULT_DOCKED_STATUS): str,
        vol.Optional(
            CONF_RETURNING_STATUS_VALUE, default=DEFAULT_RETURNING_STATUS
        ): str,
        vol.Optional(CONF_PAUSED_STATE, default=DEFAULT_PAUSED_STATE): str,
        vol.Optional(CONF_STOP_STATUS, default=DEFAULT_STOP_STATUS): str,
        vol.Optional(CONF_PAUSE_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_MODE_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_MODES, default=DEFAULT_MODES): str,
        vol.Optional(CONF_RETURN_MODE, default=DEFAULT_RETURN_MODE): str,
        vol.Optional(CONF_RETURN_HOME_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_FAN_SPEED_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_FAN_SPEEDS, default=DEFAULT_FAN_SPEEDS): str,
        vol.Optional(CONF_CLEAN_TIME_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_CLEAN_AREA_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_CLEAN_RECORD_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_LOCATE_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_FAULT_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_ROOM_CLEAN_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_ROOM_CLEAN_MODE): str,
        vol.Optional(CONF_ROOMS_DP): col_to_select(dps, is_dps=True),
        vol.Optional(CONF_ROOMS): str,
    }


class LocalTuyaVacuum(LocalTuyaEntity, StateVacuumEntity):
    """Tuya vacuum device."""

    def __init__(self, device, config_entry, switchid, **kwargs):
        """Initialize a new LocalTuyaVacuum."""
        super().__init__(device, config_entry, switchid, _LOGGER, **kwargs)
        self._state = None
        self._attrs = {}

        self._idle_status_list = []
        if self.has_config(CONF_IDLE_STATUS_VALUE):
            status = self._config[CONF_IDLE_STATUS_VALUE].split(",")
            self._idle_status_list = [state.lstrip() for state in status]

        self._modes_list = []
        if self.has_config(CONF_MODES):
            modes_list = self._config[CONF_MODES].split(",")
            self._modes_list = [mode.lstrip() for mode in modes_list]
            self._attrs[MODES_LIST] = self._modes_list

        self._returning_status_list = []
        if self.has_config(CONF_RETURNING_STATUS_VALUE):
            returning_status = self._config[CONF_RETURNING_STATUS_VALUE].split(",")
            self._returning_status_list = [state.lstrip() for state in returning_status]

        self._docked_status_list = []
        if self.has_config(CONF_DOCKED_STATUS_VALUE):
            docked_status = self._config[CONF_DOCKED_STATUS_VALUE].split(",")
            self._docked_status_list = [state.lstrip() for state in docked_status]

        self._fan_speed_list = []
        if self.has_config(CONF_FAN_SPEEDS):
            fan_speeds = self._config[CONF_FAN_SPEEDS].split(",")
            self._fan_speed_list = [speed.lstrip() for speed in fan_speeds]

        self._fan_speed = ""
        self._cleaning_mode = ""

        # Rooms (segments): reported by the vacuum in rooms_dp, restored from the
        # last state, or configured by hand in "rooms" (which wins on conflicts).
        self._device_rooms: dict[int, str] = {}
        self._config_rooms: dict[int, str] = {}
        if self.has_config(CONF_ROOMS):
            try:
                self._config_rooms = parse_rooms_config(self._config[CONF_ROOMS])
            except ValueError:
                self.error(f"Invalid rooms list: {self._config[CONF_ROOMS]}")

    @property
    def rooms(self) -> dict[int, str]:
        """Return the known rooms as {room id: name}."""
        return {**self._device_rooms, **self._config_rooms}

    def _rooms_attr(self) -> dict[str, str]:
        """Rooms as a state attribute (JSON object keys must be strings)."""
        return {str(i): name for i, name in self.rooms.items()}

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Flag supported features."""
        supported_features = (
            VacuumEntityFeature.START
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.STATUS
            | VacuumEntityFeature.STATE
        )

        if self.has_config(CONF_RETURN_HOME_DP) or (
            self.has_config(CONF_RETURN_MODE)
            and self._config[CONF_RETURN_MODE] in self._modes_list
        ):
            supported_features |= VacuumEntityFeature.RETURN_HOME
        if self.has_config(CONF_FAN_SPEED_DP):
            supported_features |= VacuumEntityFeature.FAN_SPEED
        if self.has_config(CONF_LOCATE_DP):
            supported_features |= VacuumEntityFeature.LOCATE
        if self.has_config(CONF_MODE_DP) or self.has_config(CONF_ROOM_CLEAN_DP):
            supported_features |= VacuumEntityFeature.SEND_COMMAND
        if FEATURE_CLEAN_AREA and self.has_config(CONF_ROOM_CLEAN_DP):
            supported_features |= FEATURE_CLEAN_AREA

        return supported_features

    @property
    def activity(self) -> VacuumActivity | None:
        """Return the vacuum state."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the specific state attributes of this vacuum cleaner."""
        return self._attrs

    @property
    def fan_speed(self):
        """Return the current fan speed."""
        return self._fan_speed

    @property
    def fan_speed_list(self) -> list:
        """Return the list of available fan speeds."""
        return self._fan_speed_list

    async def async_start(self, **kwargs):
        """Turn the vacuum on and start cleaning."""
        await self._device.set_dp(True, self._config[CONF_POWERGO_DP])

    async def async_stop(self, **kwargs):
        """Turn the vacuum off stopping the cleaning."""
        if (
            self.has_config(CONF_STOP_STATUS)
            and self._config[CONF_STOP_STATUS] in self._modes_list
        ):
            await self._device.set_dp(
                self._config[CONF_STOP_STATUS], self._config[CONF_MODE_DP]
            )
        else:
            await self._device.set_dp(False, self._config[CONF_POWERGO_DP])
            # _LOGGER.error("Missing command for stop in commands set.")

    async def async_pause(self, **kwargs):
        """Stop the vacuum cleaner, do not return to base."""
        if self.has_config(CONF_PAUSE_DP):
            return await self._device.set_dp(True, self._config[CONF_PAUSE_DP])

        await self.async_stop()

    async def async_return_to_base(self, **kwargs):
        """Set the vacuum cleaner to return to the dock."""
        if self.has_config(CONF_RETURN_HOME_DP):
            await self._device.set_dp(True, self._config[CONF_RETURN_HOME_DP])
        elif self.has_config(CONF_RETURN_MODE):
            await self._device.set_dp(
                self._config[CONF_RETURN_MODE], self._config[CONF_MODE_DP]
            )
        else:
            _LOGGER.error("Missing command for return home in commands set.")

    async def async_clean_spot(self, **kwargs):
        """Perform a spot clean-up."""
        return None

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        if self.has_config(CONF_LOCATE_DP):
            await self._device.set_dp(True, self._config[CONF_LOCATE_DP])

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        """Set the fan speed."""
        await self._device.set_dp(fan_speed, self._config[CONF_FAN_SPEED_DP])

    async def async_send_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner."""
        if command == "set_mode" and params and "mode" in params:
            mode = params["mode"]
            await self._device.set_dp(mode, self._config[CONF_MODE_DP])
        elif command == COMMAND_CLEAN_ROOMS:
            rooms = (params or {}).get("rooms") if isinstance(params, dict) else params
            await self.async_clean_rooms(self._resolve_rooms(rooms))

    async def async_get_segments(self) -> list:
        """Return the rooms the vacuum knows, for mapping them to areas."""
        return [Segment(id=str(i), name=name) for i, name in self.rooms.items()]

    async def async_clean_segments(self, segment_ids: list[str], **kwargs) -> None:
        """Clean the given rooms (called by vacuum.clean_area)."""
        await self.async_clean_rooms([int(segment_id) for segment_id in segment_ids])

    async def async_clean_rooms(self, room_ids: list[int]) -> None:
        """Start a room clean: power DP off, room frame, room clean mode."""
        if not self.has_config(CONF_ROOM_CLEAN_DP):
            raise HomeAssistantError("Room clean DP is not configured")
        try:
            frame = encode_room_clean(room_ids)
        except ValueError as ex:
            raise HomeAssistantError(str(ex)) from ex

        mode = self._config.get(CONF_ROOM_CLEAN_MODE) or DEFAULT_ROOM_CLEAN_MODE
        writes = [(False, self._config[CONF_POWERGO_DP])]
        writes.append((frame, self._config[CONF_ROOM_CLEAN_DP]))
        if self.has_config(CONF_MODE_DP):
            writes.append((mode, self._config[CONF_MODE_DP]))

        self.debug(f"Cleaning rooms {room_ids}: {writes}")
        for i, (value, dp) in enumerate(writes):
            if i:
                await asyncio.sleep(ROOM_CLEAN_WRITE_DELAY)
            await self._device.set_dp(value, dp)

    def _resolve_rooms(self, rooms) -> list[int]:
        """Turn room ids or names (or a comma-separated string) into ids."""
        if isinstance(rooms, (str, int)):
            rooms = str(rooms).split(",")
        if not rooms:
            raise HomeAssistantError('clean_rooms needs params: {"rooms": [ids]}')

        by_name = {name.casefold(): i for i, name in self.rooms.items()}
        room_ids = []
        for room in rooms:
            room = str(room).strip()
            if room.isdigit():
                room_ids.append(int(room))
            elif room.casefold() in by_name:
                room_ids.append(by_name[room.casefold()])
            else:
                raise HomeAssistantError(f"Unknown room: {room}")
        return room_ids

    def _update_rooms(self, rooms: dict[int, str]) -> None:
        """Store rooms reported by the vacuum, raise a repair if the map changed."""
        if rooms == self._device_rooms:
            return
        self._device_rooms = rooms
        self._attrs[ROOMS] = self._rooms_attr()

        if not FEATURE_CLEAN_AREA or self.registry_entry is None:
            return
        last_seen = self.last_seen_segments
        if last_seen is not None:
            seen = {(segment.id, segment.name) for segment in last_seen}
            now = {(str(i), name) for i, name in self.rooms.items()}
            if seen != now:
                self.async_create_segments_issue()

    def status_restored(self, stored_state):
        """Restore the rooms reported before a restart."""
        super().status_restored(stored_state)
        if rooms := stored_state.attributes.get(ROOMS):
            try:
                self._device_rooms = {int(i): str(n) for i, n in rooms.items()}
            except (AttributeError, ValueError):
                return
            self._attrs[ROOMS] = self._rooms_attr()

    def status_updated(self):
        """Device status was updated."""
        state_value = self.dp_value(self._dp_id)

        if state_value is None:
            self._state = None
        elif state_value in self._idle_status_list:
            self._state = VacuumActivity.IDLE
        elif state_value in self._docked_status_list:
            self._state = VacuumActivity.DOCKED
        elif state_value in self._returning_status_list:
            self._state = VacuumActivity.RETURNING
        elif state_value in [self._config[CONF_PAUSED_STATE], "pause"] or (
            self.dp_value(CONF_PAUSE_DP) is True
        ):
            self._state = VacuumActivity.PAUSED
        else:
            self._state = VacuumActivity.CLEANING

        self._cleaning_mode = ""
        if self.has_config(CONF_MODES):
            self._cleaning_mode = self.dp_value(CONF_MODE_DP)
            self._attrs[MODE] = self._cleaning_mode

        self._fan_speed = ""
        if self.has_config(CONF_FAN_SPEEDS):
            self._fan_speed = self.dp_value(CONF_FAN_SPEED_DP)

        if self.has_config(CONF_CLEAN_TIME_DP):
            self._attrs[CLEAN_TIME] = self.dp_value(CONF_CLEAN_TIME_DP)

        if self.has_config(CONF_CLEAN_AREA_DP):
            self._attrs[CLEAN_AREA] = self.dp_value(CONF_CLEAN_AREA_DP)

        if self.has_config(CONF_CLEAN_RECORD_DP):
            self._attrs[CLEAN_RECORD] = self.dp_value(CONF_CLEAN_RECORD_DP)

        if self.has_config(CONF_FAULT_DP):
            self._attrs[FAULT] = self.dp_value(CONF_FAULT_DP)
            if self._attrs[FAULT] != 0:
                self._state = VacuumActivity.ERROR

        if self.has_config(CONF_ROOMS_DP):
            rooms = decode_room_list(self.dp_value(CONF_ROOMS_DP))
            if rooms is not None:
                self._update_rooms(rooms)
        if self.rooms:
            self._attrs[ROOMS] = self._rooms_attr()


async_setup_entry = partial(async_setup_entry, DOMAIN, LocalTuyaVacuum, flow_schema)
