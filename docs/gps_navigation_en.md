# GPS navigation and live map

CliOS can show the vehicle's live position, heading and breadcrumb trail on a full-screen moving map, much like a Tesla's centre screen. It uses a serial NMEA GPS receiver, such as the Garmin GPS 17x HVS, or any receiver already managed by `gpsd`.

```
Garmin GPS 17x HVS ──RS-232──► USB-RS232 adapter ──► /dev/ttyUSB0
                                                         │
                         src/services/gps_service.py  ◄──┘  (or gpsd :2947)
                                  │  NMEA parser (src/gps/nmea.py)
                                  ▼
                   runtime domain "navigation" (lat, lon, heading, fix…)
                                  │  DashboardBridge.vehicleState
                                  ▼
                   UiState.qml ──► shared_pages/MapPage.qml (QtLocation + OSM tiles)
```

## Opening the map

- In the settings rail, select **Map**.
- Press **Ctrl+M** on the keyboard from anywhere to toggle between the map and the cockpit.
- A theme can call `settingsRequested("map")` from its own button.

On the map:

| Control | Action |
|---|---|
| Drag / mouse wheel / pinch | Pan and zoom (this turns off auto-follow) |
| **RECENTER** or `C` | Follow the vehicle again, with speed-based auto-zoom |
| **HEADING UP / NORTH UP** or `H` | Switch between heading-up and north-up |
| `+` / `-` | Zoom |
| `Esc` / **‹ COCKPIT** | Back to the dashboard |

## Wiring the Garmin GPS 17x HVS

1. **Power:** "HVS" means high-voltage supply. The receiver runs directly from the vehicle's 12 V supply (8–40 V), so you don't need a regulator. Feed it from a **fused** accessory circuit (1 A fuse) and connect its ground to chassis ground.
2. **Data:** Port 1 is **true RS-232 (±V levels), not 3.3 V TTL. Never connect it straight to the Raspberry Pi GPIO UART pins, because it can destroy the Pi.** Use one of these:
   - a USB-to-RS232 (DB9) adapter with an FTDI, PL2303 or CH340 chip (simplest; it appears as `/dev/ttyUSB0`), or
   - a MAX3232 level-shifter board connected to GPIO14/15 (`/dev/serial0`, after disabling the serial console in `raspi-config`).
3. Connect the GPS **data-out** lead to the adapter's **RX** (DB9 pin 2) and the GPS **ground** to the adapter's **GND** (DB9 pin 5). The data-in lead (to the adapter's TX, DB9 pin 3) is optional and only needed for reconfiguring the receiver.
4. **Wire colours:** check them against Garmin's *GPS 17x Technical Specifications* (document 190-00885-07) for your exact cable before applying power. Installers commonly report white as NMEA data out and black as ground, but the remote power-off and data-in leads must also be identified from the official table.

Mount the antenna puck with a clear view of the sky, for example on the roof or under a non-metallic part of the windscreen. Expect a first fix in 1–2 minutes after a cold start.

### Stable device name (recommended)

USB serial numbering can change between boots. Create a fixed symlink:

```bash
udevadm info -a -n /dev/ttyUSB0 | grep -E 'idVendor|idProduct|serial' | head
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="gps0"' \
  | sudo tee /etc/udev/rules.d/99-gps.rules
sudo udevadm control --reload && sudo udevadm trigger
```

Replace the vendor and product IDs with the values printed by the first command. Then set the **Serial port** setting of the GPS service to `/dev/gps0`. The CliOS user must be in the `dialout` group (`sudo usermod -aG dialout $USER`).

### Quick hardware check (without CliOS)

```bash
stty -F /dev/ttyUSB0 4800 raw && cat /dev/ttyUSB0
# Expect lines like: $GPRMC,123519,A,4807.038,N,01131.000,E,...
```

If you only see garbage, try `9600`.

## GPS service settings

In **Advanced → Services → GPS**:

| Setting | Default | Notes |
|---|---|---|
| Source | `auto` | `auto` tries the serial port first, then falls back to gpsd |
| Serial port | *(empty)* | Empty = first `/dev/serial/by-id/*`, `/dev/ttyUSB*` or `/dev/ttyACM*` |
| Serial baud rate | `auto` | `auto` probes 4800, 9600, 19200 and 38400 baud and keeps the first rate that produces valid NMEA |
| gpsd host | `127.0.0.1:2947` | Used when the source is `gpsd` |
| Minimum speed for heading | 3 km/h | Below this speed, the last heading is held. GPS course over ground is noise at standstill |
| Tile server | OSM standard | URL template using `%z/%x/%y`; see below |
| Simulation origin | Eiffel Tower | Starting point for `--mock` |

Published signals (domain `navigation`, also visible in the developer page): `latitude`, `longitude`, `altitude_m`, `gps_speed`, `heading`, `heading_valid`, `gps_fix`, `gps_mode`, `gps_quality`, `gps_satellites`, `gps_satellites_in_view`, `gps_hdop`, `gps_accuracy_m` (Garmin `PGRME`), `gps_source` and `tile_url`. Position signals become STALE after 3 s without data.

### Using gpsd instead

gpsd lets other programs (logging, chrony time sync, Navit) share the receiver:

```bash
sudo apt install gpsd gpsd-clients
sudo sed -i 's|^DEVICES=.*|DEVICES="/dev/gps0"|' /etc/default/gpsd
sudo systemctl enable --now gpsd
cgps   # check the fix
```

Then set **Source** to `gpsd`.

## Map tiles

The map uses Qt Location's OSM plugin with a configurable tile URL. Viewed tiles are cached on disk (256 MB, under `~/.cache/QtLocation`), so roads you've already driven still display without network access.

- **Default** (`https://tile.openstreetmap.org/%z/%x/%y.png`): fine for personal, light use. Follow the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/) and don't bulk-download.
- **Dark / night map:** point the URL at any dark raster style you're licensed to use, for example a self-hosted style or a provider that requires an API key.
- **Fully offline:** serve your region's tiles locally, for example with `tileserver-gl` and an OpenMapTiles `.mbtiles` extract, then set the URL to `http://127.0.0.1:8080/styles/basic/%z/%x/%y.png`.

When you change the tile URL, reopen the map to load the new tiles.

## Testing without hardware

`./clios --mock` simulates a GPS that drives a loop around **Simulation origin** at the simulated vehicle speed. Use the mock control panel to change the speed.

## Raspberry Pi 3B notes

CliOS officially targets the Raspberry Pi 5, and the Pi 4 is experimental. A Pi 3B (1 GB RAM) can run the map, but expect a lower frame rate. To reduce the load:

- use Raspberry Pi OS **64-bit** (the PySide6 wheels are aarch64 only);
- keep the map page closed when you don't need it (it is loaded on demand and fully unloaded on exit);
- disable services you don't use (engine sound, cabin noise);
- prefer a Pi 4 or 5 if you have one available.

## Ideas for going further

- **Heading at standstill and in tunnels:** add an IMU/compass (BNO085 or similar) and fuse it with the GPS course and CAN wheel speed for dead reckoning.
- **Turn-by-turn routing:** run an offline router (OSRM or Valhalla) on the Pi and draw the route with a `MapPolyline`.
- **Embedded mini-map:** reuse `MapPage.qml` elements inside a theme's `Dashboard.qml` for a split cluster-and-map layout.
- **Trip logging:** record the `navigation` domain alongside the trip statistics and export it as GPX.
