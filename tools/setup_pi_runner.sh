#!/usr/bin/env bash
# Installs a GitHub Actions self-hosted runner on the car's Raspberry Pi so the
# "Hardware check" workflow (.github/workflows/hardware.yml) can test the real
# GPS receiver, CAN adapter and OBD-II connection.
#
# Usage (as your normal user, not root):
#   ./tools/setup_pi_runner.sh <registration-token> [repository-url]
#
# Get the token from GitHub: repository Settings -> Actions -> Runners ->
# New self-hosted runner (the value after --token). It expires after 1 hour.
set -euo pipefail

TOKEN="${1:-}"
REPO_URL="${2:-https://github.com/gobblenet/CliOS}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
LABELS="clios-pi"

if [[ -z "$TOKEN" ]]; then
    echo "Usage: $0 <registration-token> [repository-url]" >&2
    echo "Get the token from Settings -> Actions -> Runners -> New self-hosted runner." >&2
    exit 2
fi
if [[ $EUID -eq 0 ]]; then
    echo "[ERROR] Run this as your normal user, not root (the script uses sudo where needed)." >&2
    exit 2
fi

case "$(uname -m)" in
    aarch64|arm64) RUNNER_ARCH="arm64" ;;
    armv7l|armv6l) RUNNER_ARCH="arm" ;;
    x86_64) RUNNER_ARCH="x64" ;;
    *) echo "[ERROR] Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

echo "▶ [1/5] Installing system packages (curl, Python venv, CAN tools)..."
sudo apt-get update -y
sudo apt-get install -y curl python3-venv python3-pip can-utils

echo "▶ [2/5] Finding the latest GitHub Actions runner release..."
RELEASE_JSON="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest)"
VERSION="$(printf '%s' "$RELEASE_JSON" | grep -m1 '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')"
if [[ -z "$VERSION" ]]; then
    echo "[ERROR] Could not read the latest runner version from GitHub." >&2
    exit 1
fi
ARCHIVE="actions-runner-linux-${RUNNER_ARCH}-${VERSION}.tar.gz"
# The release notes publish one SHA-256 per archive between these markers.
EXPECTED_SHA="$(printf '%s' "$RELEASE_JSON" \
    | grep -o "BEGIN SHA linux-${RUNNER_ARCH} -->[0-9a-f]*" | sed 's/.*-->//' || true)"
echo "    Runner ${VERSION} for linux-${RUNNER_ARCH}"

echo "▶ [3/5] Downloading and verifying the runner into ${RUNNER_DIR}..."
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
if [[ -f .runner ]]; then
    echo "[ERROR] A runner is already configured in ${RUNNER_DIR}." >&2
    echo "        Remove it first: cd ${RUNNER_DIR} && sudo ./svc.sh uninstall && ./config.sh remove --token <token>" >&2
    exit 1
fi
curl -fsSL -o "$ARCHIVE" "https://github.com/actions/runner/releases/download/v${VERSION}/${ARCHIVE}"
if [[ -n "$EXPECTED_SHA" ]]; then
    echo "${EXPECTED_SHA}  ${ARCHIVE}" | sha256sum -c -
else
    echo "    ⚠ No published checksum found; skipping verification."
fi
tar xzf "$ARCHIVE"
rm -f "$ARCHIVE"

echo "▶ [4/5] Registering the runner with ${REPO_URL}..."
./config.sh --unattended --replace \
    --url "$REPO_URL" \
    --token "$TOKEN" \
    --name "$(hostname)-clios" \
    --labels "$LABELS"

echo "▶ [5/5] Installing the runner as a service that starts at boot..."
# Serial devices (GPS, ELM327) need the dialout group.
sudo usermod -a -G dialout "$USER"
sudo ./svc.sh install "$USER"
sudo ./svc.sh start

echo ""
echo "✓ Runner installed. It should appear as Idle under Settings -> Actions -> Runners."
echo "  Run the check from the Actions tab: Hardware check -> Run workflow."
