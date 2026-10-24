> [!NOTE]
> **This is a personal fork of [xZetsubou/hass-localtuya](https://github.com/xZetsubou/hass-localtuya).**
> It is not maintained by or affiliated with the upstream project. It follows upstream `master` and adds
> a few vacuum improvements, developed and tested with a **Lefant M5** robot vacuum. Changes intended for
> upstream are offered there as pull requests. For everything else, use the upstream integration and its
> documentation and issue tracker.

## Changes in this fork

Modified by [lauff](https://github.com/lauff), October 2026 (see the commit history for details).
All changes are opt-in: existing configurations behave exactly as in upstream.

| Change | Branch | Upstream |
|---|---|---|
| **Fix:** `vacuum.send_command` without `params` no longer raises a `TypeError` | `fix/vacuum-send-command-params` | not yet proposed |
| **Vacuum option "Return home DP":** `return_to_base` writes `True` to this DP (Tuya `switch_charge`) instead of writing a mode | `feat/vacuum-return-home-dp` | not yet proposed |
| **Clean selected rooms:** Home Assistant "clean by area" (`vacuum.clean_area`, HA ≥ 2026.3) and a `clean_rooms` command; the vacuum entity now also advertises `send_command` | `feat/vacuum-clean-area` | not yet proposed |

New vacuum options for room cleaning:

| Option | Meaning |
|---|---|
| Room clean DP | DP the room frame is written to; enables room cleaning |
| Room clean mode | value written to the Mode DP after the frame (default `CleanModeSectorbased`) |
| Room list DP | DP in which the vacuum reports its rooms (id and name) |
| Rooms | `id:name,id:name,...`, fallback and name override for the room list |

A room clean writes, about 100 ms apart: Power DP = `False`, the room frame, then the room clean mode.
The room frame format (`aa 00 LEN 14 01 COUNT IDS... CHK`) was captured from the Lefant app. Other
vacuums may use a different format, see [`core/vacuum_rooms.py`](custom_components/localtuya/core/vacuum_rooms.py).

<details><summary>Example: Lefant M5</summary>

Device: protocol 3.5, Manual DPS `2,3,113,183`. Vacuum entity: Status DP 5, Power DP 1, Pause DP 2,
Return home DP 3, Mode DP 4 (`smart,CleanModeSectorbased,zone`), Fan speed DP 9
(`gentle,normal,strong,superStrong`), Clean time DP 16, Clean area DP 17, Fault DP 164,
Room clean DP 113, Room list DP 183. Map the rooms to areas in the vacuum entity's settings, then:

```yaml
action: vacuum.clean_area
target:
  entity_id: vacuum.lefant_m5
data:
  cleaning_area_id: [hall, floor]
```

or, without area mapping:

```yaml
action: vacuum.send_command
target:
  entity_id: vacuum.lefant_m5
data:
  command: clean_rooms
  params:
    rooms: [Hall, 7]   # room names or ids, in cleaning order
```
</details>

### Installing this fork

In HACS remove the upstream "Local Tuya" repository (keep the integration and its devices), then add
`https://github.com/lauff/hass-localtuya` as a custom repository of type *Integration*, install it and
restart Home Assistant. Both use the domain `localtuya`, so existing devices and entities are kept.
Back up Home Assistant first. To go back, do the same with the upstream repository.

[![Open this fork in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&repository=hass-localtuya&owner=lauff)

---

*Original upstream README:*

<a  href="https://www.buymeacoffee.com/mrbanderx3"  target="_blank"><img  src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png"  alt="Buy Me A Coffee"  style="height: 30px !important;width: 150px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

---


![logo](https://github.com/rospogrigio/localtuya-homeassistant/blob/master/img/logo-small.png)


__A Home Assistant custom Integration for local handling of Tuya-based devices.__

### **Usage and setup [Documentation](https://xzetsubou.github.io/hass-localtuya/)**

<br>

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&repository=hass-localtuya&owner=xZetsubou)



## __𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬__
- Supported Sub-devices - `Devices that function through gateways`
- Remote entities - `Supports IR remotes through native remote entity`
- Auto-configure devices - `Requires a cloud API setup`
- Automatic insertion - `Some fields requires a cloud API setup`
- Devices discovery - `Discovers Tuya devices on your network`
- Cloud API - `Only to help you to setup devices, can work without it.`



<br>

[𝐑𝐞𝐩𝐨𝐫𝐭𝐢𝐧𝐠 𝐚𝐧 𝐢𝐬𝐬𝐮𝐞](https://xzetsubou.github.io/hass-localtuya/report_issue/)

<!-- ### Notes

* Do not declare anything as "tuya", such as by initiating a "switch.tuya". Using "tuya" launches Home Assistant's built-in, cloud-based Tuya integration in lieu of localtuya.

* This custom integration updates device status via pushing updates instead of polling, so status updates are fast (even when manually operated).

* The integration also supports the Tuya IoT Cloud APIs, for the retrieval of info and of the local_keys of the devices. 
The Cloud API account configuration is not mandatory (LocalTuya can work also without it) but is strongly suggested for easy retrieval (and auto-update after re-pairing a device) of local_keys. Cloud API calls are performed only at startup, and when a local_key update is needed. -->

<details><summary> 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 </summary>
<p>
    
[rospogrigio](https://github.com/rospogrigio), the original maintainer of LocalTuya. This fork was created when the [upstream](https://github.com/rospogrigio/localtuya) version was at `v5.2.1`.

[NameLessJedi](https://github.com/NameLessJedi/localtuya-homeassistant) and [mileperhour](https://github.com/mileperhour/localtuya-homeassistant) being the major sources of inspiration, and whose code for switches is substantially unchanged.

[TradeFace](https://github.com/TradeFace), for being the only one to provide the correct code for communication with the cover (in particular, the 0x0d command for the status instead of the 0x0a, and related needs such as double reply to be received): 

sean6541, for the working (standard) Python Handler for Tuya devices.

[jasonacox](https://github.com/jasonacox), for the [TinyTuya](https://github.com/jasonacox/tinytuya) project from where I got big help and references to upgrade integration.

[uzlonewolf](https://github.com/uzlonewolf), for maintaining TinyTuya who improved the tool so much and introduced new features like new protocols, etc.

[postlund](https://github.com/postlund), for the ideas, for coding 95% of the refactoring and boosting the quality of the upstream repository.

</p>
</details> 
