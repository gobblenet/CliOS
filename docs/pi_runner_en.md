# Hardware testing on the Raspberry Pi (self-hosted runner)

The regular CI (`.github/workflows/ci.yml`) runs on GitHub's cloud machines and cannot see your GPS receiver or CAN adapter. The **Hardware check** workflow (`.github/workflows/hardware.yml`) runs on the car's Raspberry Pi through a GitHub Actions self-hosted runner and checks the real hardware:

| Check | Passes when | Skipped when |
|---|---|---|
| GPS | The receiver sends valid NMEA sentences (4800, 9600, 19200 or 38400 baud). Reports the fix and satellite count. | No serial adapter is plugged in |
| CAN | The `can0` interface exists and is up | `can0` does not exist |
| OBD (CAN) | An ECU answers on `can0`. Reports the supported PIDs and sample readings (RPM, speed, coolant, battery). | `can0` is down, or no ECU answers (ignition off) |
| OBD (ELM327) | Only when a port is given: the adapter and an ECU answer | The port does not exist |

The workflow also runs the GPS and hardware-check unit tests on the Pi.

## One-time setup on the Pi

1. Use 64-bit Raspberry Pi OS (Bookworm) and clone CliOS on the Pi:
   ```bash
   git clone https://github.com/gobblenet/CliOS.git
   cd CliOS
   ```
2. On GitHub, open **Settings → Actions → Runners → New self-hosted runner**. Copy only the token: the long value after `--token` in the "Configure" commands. It expires after one hour.
3. On the Pi, run the setup script with that token:
   ```bash
   ./tools/setup_pi_runner.sh <token>
   ```
   As your normal user (not root), the script:
   - installs `curl`, `python3-venv` and `can-utils`;
   - downloads the latest GitHub runner for your Pi's architecture and verifies its checksum;
   - registers it with the label `clios-pi`;
   - adds you to the `dialout` group for serial devices;
   - installs the runner as a service that starts at boot.
4. Back on **Settings → Actions → Runners**, the runner `<hostname>-clios` should show as **Idle**.

The Pi needs internet access (Wi-Fi or phone hotspot) to pick up jobs. When it's offline, jobs wait in the queue until it reconnects.

## Running the check

On GitHub, open **Actions → Hardware check → Run workflow**. The options are:
- **Require GPS** (on by default): fail if the GPS doesn't send valid NMEA.
- **Require OBD**: fail if no ECU answers. Turn the ignition on first.
- **GPS port / ELM327 port**: set these if you use fixed device names such as `/dev/gps0`.

The workflow also runs after every push to `main`, in report-only mode: it fails only if the unit tests fail, not if the car is off.

You can run the same check by hand on the Pi:
```bash
python3 tools/hardware_check.py --require-gps
```

## Security

A self-hosted runner executes workflow code on the Pi, which is wired into your car. To keep that safe:
- The Hardware check workflow only runs on manual runs and on pushes to `main`. It never runs on pull requests, so code from other people's forks cannot reach your Pi.
- Only add the `clios-pi` label to workflows you trust.
- If the repository is public, keep this rule: never add `pull_request` triggers to jobs that use `runs-on: [self-hosted, ...]`.

To remove the runner, run `cd ~/actions-runner && sudo ./svc.sh uninstall && ./config.sh remove --token <token>`, with a removal token from the same Runners page.
