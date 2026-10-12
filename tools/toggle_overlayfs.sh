#!/usr/bin/env bash
# ==============================================================================
# CliOS - Bascule de la protection SD (OverlayFS Raspberry Pi)
# ==============================================================================

set -eo pipefail

if ! command -v raspi-config &>/dev/null; then
    echo -e "\033[1;33m[WARNING] raspi-config is not installed on this system.\033[0m"
    echo "This feature is only available on Raspberry Pi OS."
    exit 1
fi

# Récupération de l'état actuel : 0 = activé (Read-Only), 1 = désactivé (Read-Write).
# -n interdit toute attente de mot de passe dans Cage ; l'installateur fournit
# une règle sudoers limitée à ces trois commandes exactes.
if ! STATUS="$(sudo -n /usr/bin/raspi-config nonint get_overlay_now 2>/dev/null)"; then
    echo -e "\033[1;31m[ERROR] OverlayFS permission missing. Run install.sh again.\033[0m" >&2
    exit 1
fi

if [[ "$STATUS" == "0" ]]; then
    echo -e "\033[1;33m[INFO] Disabling OverlayFS protection (switching to read/write mode)...\033[0m"
    sudo -n /usr/bin/raspi-config nonint disable_overlayfs
    echo -e "\033[1;32m✓ SD protection disabled. Reboot the Raspberry Pi to apply.\033[0m"
else
    echo -e "\033[1;34m[INFO] Enabling OverlayFS protection (switching to read-only mode)...\033[0m"
    sudo -n /usr/bin/raspi-config nonint enable_overlayfs
    echo -e "\033[1;32m✓ SD protection enabled. Reboot the Raspberry Pi to apply.\033[0m"
fi
