# Live vehicle data and alarms

The **Données** screen lets you watch any signal CliOS knows about as large tiles. Each tile shows the current value, its min/max since the screen opened, a 60-second trend line, and optional alarm limits. When a value goes out of range, a red banner appears on **every** screen until it returns to normal.

Signals come from several sources, all shown in the same place:

| Source | Runtime domain | Works on |
|---|---|---|
| **OBD-II live data** (new `clios.obd_live` service) | `obd` | Almost any car built since about 2001 (petrol, US) / 2004 (diesel, EU). Requires CAN-based OBD (ISO 15765), which covers most cars from 2008 |
| Vehicle CAN profile (`data/can/*.json`) | `powertrain`, `motion`, `body`… | Cars with a CAN dictionary (currently the Clio 3) |
| GPS service | `navigation` | Any NMEA GPS or gpsd |
| CliOS services | `environment`, `trip`, `system`… | Always |

## Opening the screen

- In the settings rail, select **Données**.
- Press **Ctrl+D** from anywhere.
- Tap the red alarm banner.

| Action | How |
|---|---|
| Add a signal | **MODIFIER** → **+ AJOUTER UN SIGNAL**, then type to filter (e.g. `temp`, `obd`, `volt`) |
| Reorder / remove | **MODIFIER** → ◀ ▶ / ✕ |
| Set alarm limits | Long-press a tile, or **MODIFIER** → ✎. Leave a field empty to disable that limit |
| Reset min/max | Double-click a tile |
| Restore the default layout | **MODIFIER** → **RÉINITIALISER** |

The layout and limits are saved in the active vehicle configuration under `ui.live_tiles`.

Tile colours: **amber** means within 5 % of a limit, **red/blinking** means out of range, and **grey "PÉRIMÉ"** means the signal stopped updating (adapter unplugged, ignition off). Stale values never raise alarms.

The default layout is OBD-II based: RPM, speed, coolant (alarm > 105 °C), battery voltage (alarm < 12.0 V or > 15.0 V), load, intake air (> 60 °C), oil (> 125 °C), fuel level (< 10 %), throttle, MAF, fuel rate and stored fault count (> 0). Only the PIDs your car supports will show values; you can remove the others.

## Connecting to the car

The OBD-II service only sends **read-only** mode 01 requests. It never writes to the car or clears codes. It discovers the supported PIDs automatically, polls the fast ones (RPM, speed, load, throttle, MAF, fuel rate…) every cycle, and rotates through the slow ones (temperatures, levels, counters). It also pauses while a fault-code scan (Diagnostic page) runs.

**Option A: CAN adapter (fastest, recommended).** Expect about 20–50 PIDs per second.

- **PiCCANTE** (Raspberry Pi Pico + CAN transceiver) exposed over SLCAN:
  ```bash
  sudo apt install can-utils
  sudo slcand -o -s6 -t hw -S 3000000 /dev/ttyACM1 can0   # -s6 = 500 kbit/s
  sudo ip link set can0 up
  ```
- **CANable / candleLight** (gs_usb): `sudo ip link set can0 up type can bitrate 500000`.

Wire CAN-H/CAN-L to OBD pins 6 and 14 and ground to pin 5. Most cars use 500 kbit/s on the OBD port, and some use 250 kbit/s. CliOS uses `can0` for both the vehicle profile and OBD, and the OBD service's **Interface** setting `auto` picks CAN whenever the bus is connected.

**Option B: ELM327 adapter (easiest).** Slower, about 5–10 PIDs per second.

- **USB:** set **Port ELM327** to its device (e.g. `/dev/ttyUSB1`, or better a `/dev/serial/by-id/...` path).
- **Bluetooth:** pair it once, then bind it to `/dev/rfcomm0` (the default):
  ```bash
  bluetoothctl   # power on / scan on / pair XX:XX:XX:XX:XX:XX / trust XX:XX:XX:XX:XX:XX
  sudo rfcomm bind 0 XX:XX:XX:XX:XX:XX
  ```
- Set **Interface** to `elm327`. **Débit ELM327** `auto` tries 38400, 115200, 9600 and 500000 baud.

> If you use both a USB GPS and a USB ELM327, give each a fixed `/dev/serial/by-id/...` path (or a udev symlink, see `gps_navigation_en.md`), so the GPS service's auto-detection doesn't open the OBD adapter.

## OBD service settings

In **Avancé → Services → OBD**:

| Setting | Default | Notes |
|---|---|---|
| Interface | `auto` | `auto` = CAN if connected, otherwise ELM327 |
| Port ELM327 | `/dev/rfcomm0` | Serial device of the ELM327 |
| Débit ELM327 | `auto` | Serial speed |
| Pause entre cycles | 0 ms | Increase to reduce bus load |

Status signals: `obd.obd_connected`, `obd.obd_interface`, `obd.obd_supported_pids`, `obd.mil_on` (check-engine light) and `obd.dtc_count`. Read the actual fault codes on the **Diagnostic** page.

## Testing without a car

`./clios --mock` simulates an ECU that answers 14 standard PIDs from the physics model. Use the mock control panel to rev the engine and watch the tiles, or add a DTC in a scenario to see the check-engine alarm.

## Adding more signals

- **Any standard PID:** add a `PidDefinition` to `src/obd/pids.py` and its label to `frontend/state/SignalCatalog.js` (a unit test checks that every PID has a label).
- **Manufacturer CAN frames** (doors, TPMS, gearbox temperature…): describe them in a vehicle CAN dictionary (`data/can/`, see `community_en.md`). They appear in the signal picker automatically.
