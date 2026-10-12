#!/usr/bin/env bash
# ==============================================================================
#  ____ _ _  ___  ____  
# / ___| (_)/ _ \/ ___| 
#| |   | | | | | \___ \ 
#| |___| | | |_| |___) |
# \____|_|_|\___/|____/ 
#
# CliOS - Installateur Interactif & Gestionnaire de Déploiement
# Description: Prépare les dépendances système, compile pyo, configure l'environnement
#              virtuel .venv, les règles udev, les services CAN et l'autostart Kiosk.
# ==============================================================================

set -eo pipefail

# ------------------------------------------------------------------------------
# 1. Variables & Chemins
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
CURRENT_USER="${SUDO_USER:-${USER:-$(id -un 2>/dev/null || whoami)}}"
VENV_DIR="${PROJECT_DIR}/.venv"
INSTALL_ETC_DIR="${PROJECT_DIR}/installation/etc"

# Si un venv est actuellement actif dans le terminal appelant, on le désactive pour ce sous-shell
if [[ -n "$VIRTUAL_ENV" ]]; then
    PATH="${PATH//${VIRTUAL_ENV}\/bin:/}"
    unset VIRTUAL_ENV
fi

SYSTEMD_DIR="/etc/systemd/system"
UDEV_RULES_DIR="/etc/udev/rules.d"
LOCAL_LIBEXEC_DIR="/usr/local/libexec"
POLKIT_RULES_DIR="/etc/polkit-1/rules.d"
SUDOERS_DIR="/etc/sudoers.d"

# Flags d'exécution
DRY_RUN=0
VENV_ONLY=0
NON_INTERACTIVE=0
DO_UNINSTALL=0
KIOSK_INSTALLED=0
KIOSK_AUTOSTART_ENABLED=0
FAST_BOOT_APPLIED=()
FAST_BOOT_SKIPPED=()

# ------------------------------------------------------------------------------
# 2. Couleurs & Mise en page CLI
# ------------------------------------------------------------------------------
if [[ -t 1 ]]; then
    C_RESET="\033[0m"
    C_BOLD="\033[1m"
    C_DIM="\033[2m"
    C_RED="\033[1;31m"
    C_GREEN="\033[1;32m"
    C_YELLOW="\033[1;33m"
    C_BLUE="\033[1;34m"
    C_MAGENTA="\033[1;35m"
    C_CYAN="\033[1;36m"
    C_WHITE="\033[1;37m"
else
    C_RESET=""
    C_BOLD=""
    C_DIM=""
    C_RED=""
    C_GREEN=""
    C_YELLOW=""
    C_BLUE=""
    C_MAGENTA=""
    C_CYAN=""
    C_WHITE=""
fi

print_banner() {
    echo -e "${C_CYAN}${C_BOLD}"
    cat << "EOF"
   ____ _ _  ___  ____  
  / ___| (_)/ _ \/ ___| 
 | |   | | | | | \___ \ 
 | |___| | | |_| |___) |
  \____|_|_|\___/|____/ 
EOF
    echo -e "${C_RESET}${C_WHITE}${C_BOLD} Modular Automotive Dashboard${C_RESET}"
    echo -e "${C_DIM} Installation & system setup assistant${C_RESET}"
    echo -e "${C_DIM} Target folder: ${PROJECT_DIR}${C_RESET}"
    echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════${C_RESET}\n"
}

log_step() {
    echo -e "\n${C_BLUE}${C_BOLD}▶ [$1] $2${C_RESET}"
    echo -e "${C_DIM}──────────────────────────────────────────────────────────────────${C_RESET}"
}

log_info() {
    echo -e " ${C_CYAN}ℹ${C_RESET} $1"
}

log_success() {
    echo -e " ${C_GREEN}✓${C_RESET} $1"
}

log_warn() {
    echo -e " ${C_YELLOW}⚠${C_RESET} ${C_BOLD}$1${C_RESET}"
}

log_error() {
    echo -e " ${C_RED}✗ ERROR:${C_RESET} $1" >&2
}

log_dry() {
    echo -e " ${C_MAGENTA}[DRY-RUN]${C_RESET} ${C_DIM}$1${C_RESET}"
}

# ------------------------------------------------------------------------------
# 3. Fonctions Utilitaires
# ------------------------------------------------------------------------------
run_cmd() {
    local cmd_desc="$1"
    shift
    if [[ $DRY_RUN -eq 1 ]]; then
        log_dry "Simulated command: $*"
        return 0
    fi
    log_info "$cmd_desc"
    "$@"
}

run_sudo_cmd() {
    local cmd_desc="$1"
    shift
    if [[ $DRY_RUN -eq 1 ]]; then
        log_dry "Simulated sudo command: sudo $*"
        return 0
    fi
    log_info "$cmd_desc"
    if [[ $EUID -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

run_target_cmd() {
    local cmd_desc="$1"
    shift
    if [[ $DRY_RUN -eq 1 ]]; then
        log_dry "Simulated user command: $*"
        return 0
    fi
    log_info "$cmd_desc"
    if [[ $EUID -eq 0 && "$(id -un)" != "$CURRENT_USER" ]]; then
        runuser -u "$CURRENT_USER" -- "$@"
    else
        "$@"
    fi
}

safe_systemctl() {
    local action_desc="$1"
    shift
    if command -v systemctl &>/dev/null; then
        run_sudo_cmd "$action_desc" systemctl "$@"
    else
        log_info "systemctl not available in this environment (${action_desc} skipped)."
    fi
}

systemd_unit_exists() {
    local unit="$1"
    if [[ $DRY_RUN -eq 1 ]]; then
        return 0
    fi
    command -v systemctl &>/dev/null && systemctl cat "$unit" &>/dev/null
}

disable_systemd_unit_if_present() {
    local unit="$1"
    if systemd_unit_exists "$unit"; then
        safe_systemctl "Disabling ${unit}" disable "$unit" 2>/dev/null || true
    else
        log_info "${unit} not present: nothing to do."
    fi
}

safe_udevadm() {
    local action_desc="$1"
    shift
    if command -v udevadm &>/dev/null; then
        run_sudo_cmd "$action_desc" udevadm "$@"
    else
        log_info "udevadm not available in this environment (${action_desc} skipped)."
    fi
}

backup_system_file() {
    local file_path="$1"
    if [[ -f "$file_path" ]]; then
        local timestamp
        timestamp=$(date +"%Y%m%d_%H%M%S")
        local backup_path="${file_path}.bak_${timestamp}"
        log_warn "Existing file detected: ${file_path}"
        if [[ $DRY_RUN -eq 1 ]]; then
            log_dry "Simulated backup: ${file_path} -> ${backup_path}"
        else
            if [[ $EUID -eq 0 ]]; then
                cp "$file_path" "$backup_path"
            else
                sudo cp "$file_path" "$backup_path"
            fi
            log_success "Backup created: ${backup_path}"
        fi
    fi
}

install_release_tree() {
    local release_dir="$1"
    local release_parent staging_dir previous_dir source_archive
    local source_device target_device

    release_parent="$(dirname "$release_dir")"
    staging_dir="${release_dir}.installing"
    previous_dir="${release_dir}.previous-install"

    source_device="$(stat -c %d "$VENV_DIR")"
    target_device="$(stat -c %d "$release_parent")"
    if [[ "$source_device" != "$target_device" ]]; then
        log_error "The project and ${release_parent} must be on the same filesystem to move the .venv without copying."
        log_error "First copy CliOS to /home/${CURRENT_USER}, then run install.sh again."
        return 1
    fi

    source_archive="$(mktemp /tmp/clios-release-tree.XXXXXX.tar)"
    if ! tar \
        --exclude='./.git' \
        --exclude='./.venv' \
        --exclude='./__pycache__' \
        --exclude='*/__pycache__' \
        --exclude='./.idea' \
        --exclude='./.pytest_cache' \
        --exclude='./.portfolio' \
        --exclude='./dist' \
        --exclude='./wheelhouses' \
        --exclude='.DS_Store' \
        -C "$PROJECT_DIR" -cf "$source_archive" .; then
        rm -f "$source_archive"
        log_error "Could not prepare the release files."
        return 1
    fi

    run_sudo_cmd "Cleaning up release staging" rm -rf "$staging_dir" "$previous_dir"
    run_sudo_cmd "Creating release staging" mkdir -p "$staging_dir"
    if ! run_sudo_cmd "Installing the release code" tar -C "$staging_dir" -xf "$source_archive"; then
        rm -f "$source_archive"
        run_sudo_cmd "Cleaning up incomplete staging" rm -rf "$staging_dir"
        return 1
    fi
    rm -f "$source_archive"

    # /home et /opt partagent normalement la partition racine. Un renommage ne
    # relit pas les gros fichiers Qt et conserve un environnement isolé par release.
    if ! run_sudo_cmd "Moving the Python environment into the release" mv "$VENV_DIR" "${staging_dir}/.venv"; then
        run_sudo_cmd "Cleaning up incomplete staging" rm -rf "$staging_dir"
        return 1
    fi

    # Actualise pyvenv.cfg et les lanceurs standards après le changement de chemin.
    if ! run_sudo_cmd "Updating the Python environment path" \
        "$PYTHON_BIN" -m venv --upgrade "${staging_dir}/.venv"; then
        run_sudo_cmd "Restoring the source Python environment" mv "${staging_dir}/.venv" "$VENV_DIR"
        run_sudo_cmd "Cleaning up incomplete staging" rm -rf "$staging_dir"
        return 1
    fi

    if ! run_target_cmd "Release Python self-check" \
        "${staging_dir}/.venv/bin/python3" -c "import PySide6, numpy, psutil, can, serial, pyudev"; then
        run_sudo_cmd "Restoring the source Python environment" mv "${staging_dir}/.venv" "$VENV_DIR"
        run_sudo_cmd "Cleaning up incomplete staging" rm -rf "$staging_dir"
        return 1
    fi
    if ! run_sudo_cmd "Python precompilation for first start" \
        "${staging_dir}/.venv/bin/python3" -m compileall -q \
        "${staging_dir}/main.py" "${staging_dir}/src" "${staging_dir}/tools"; then
        run_sudo_cmd "Restoring the source Python environment" mv "${staging_dir}/.venv" "$VENV_DIR"
        run_sudo_cmd "Cleaning up incomplete staging" rm -rf "$staging_dir"
        return 1
    fi
    if [[ -f "${staging_dir}/tools/qml_smoke.py" ]] && ! run_target_cmd "Release QML self-check" \
        env QT_QPA_PLATFORM=minimal QT_QUICK_BACKEND=software QSG_RENDER_LOOP=basic \
        "${staging_dir}/.venv/bin/python3" "${staging_dir}/tools/qml_smoke.py" --validate-only; then
        run_sudo_cmd "Restoring the source Python environment" mv "${staging_dir}/.venv" "$VENV_DIR"
        run_sudo_cmd "Cleaning up incomplete staging" rm -rf "$staging_dir"
        return 1
    fi

    if [[ -e "$release_dir" || -L "$release_dir" ]]; then
        run_sudo_cmd "Setting aside the incomplete or previous release" mv "$release_dir" "$previous_dir"
    fi
    if ! run_sudo_cmd "Atomic release validation" mv "$staging_dir" "$release_dir"; then
        if [[ -e "$previous_dir" || -L "$previous_dir" ]]; then
            run_sudo_cmd "Restoring the previous release" mv "$previous_dir" "$release_dir"
        fi
        return 1
    fi
    run_sudo_cmd "Cleaning up the previous installation" rm -rf "$previous_dir" \
        || log_warn "The old staging ${previous_dir} must be removed manually."
}

prompt_confirm() {
    local message="$1"
    local default="${2:-Y}" # Y ou N
    if [[ $NON_INTERACTIVE -eq 1 ]]; then
        if [[ "$default" =~ ^[Yy]$ ]]; then return 0; else return 1; fi
    fi

    local prompt_text
    if [[ "$default" =~ ^[Yy]$ ]]; then
        prompt_text="${C_BOLD}${message}${C_RESET} [Y/n]: "
    else
        prompt_text="${C_BOLD}${message}${C_RESET} [y/N]: "
    fi

    while true; do
        read -r -p "$(echo -e "${prompt_text}")" response
        response="${response:-$default}"
        case "$response" in
            [oOyY][uUeE][sS]|[oOyY])
                return 0
                ;;
            [nN][oO]|[nN])
                return 1
                ;;
            *)
                echo -e " ${C_YELLOW}Please answer 'y' (yes) or 'n' (no).${C_RESET}"
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# 4. Désinstallation propre
# ------------------------------------------------------------------------------
do_uninstall() {
    print_banner
    log_step "UNINSTALL" "Removing system services and configuration"

    if prompt_confirm "Disable and remove the CliOS services from /etc/systemd and /etc/udev?" "N"; then
        safe_systemctl "Stopping CliOS USB mounts" stop "clios-usb-mount@*.service" 2>/dev/null || true
        local services=("clios.service" "clios-updater.service" "clios-updater.socket" "clios-usb-mount@.service" "can-usb.service" "can-wake.service" "slcan.service")
        for srv in "${services[@]}"; do
            if [[ -f "${SYSTEMD_DIR}/${srv}" ]]; then
                log_info "Disabling service ${srv}..."
                safe_systemctl "Stopping and disabling ${srv}" disable --now "${srv}" 2>/dev/null || true
                run_sudo_cmd "Removing ${SYSTEMD_DIR}/${srv}" rm -f "${SYSTEMD_DIR}/${srv}"
                log_success "Service ${srv} removed."
            fi
        done

        if [[ -f "${UDEV_RULES_DIR}/99-slcan.rules" ]]; then
            run_sudo_cmd "Removing ${UDEV_RULES_DIR}/99-slcan.rules" rm -f "${UDEV_RULES_DIR}/99-slcan.rules"
            log_success "udev rules removed."
        fi

        if [[ -f "${UDEV_RULES_DIR}/90-clios-usb-storage.rules" ]]; then
            run_sudo_cmd "Removing ${UDEV_RULES_DIR}/90-clios-usb-storage.rules" rm -f "${UDEV_RULES_DIR}/90-clios-usb-storage.rules"
            log_success "USB storage rule removed."
        fi

        if [[ -f "${LOCAL_LIBEXEC_DIR}/clios-usb-mount" ]]; then
            run_sudo_cmd "Removing the USB mount helper" rm -f "${LOCAL_LIBEXEC_DIR}/clios-usb-mount"
        fi

        if [[ -f "${SUDOERS_DIR}/clios-overlayfs" ]]; then
            run_sudo_cmd "Removing the OverlayFS permission" rm -f "${SUDOERS_DIR}/clios-overlayfs"
        fi

        if [[ -f "${POLKIT_RULES_DIR}/49-clios-power.rules" ]]; then
            run_sudo_cmd "Removing the CliOS Polkit rule" rm -f "${POLKIT_RULES_DIR}/49-clios-power.rules"
        fi

        safe_systemctl "Reloading systemd and udev" daemon-reload
        safe_udevadm "Reloading udev rules" control --reload-rules 2>/dev/null || true
        log_success "System services cleaned up."
    else
        log_info "Skipped removing system services."
    fi

    if prompt_confirm "Also remove the Python .venv environment?" "N"; then
        if [[ -d "$VENV_DIR" ]]; then
            run_cmd "Removing the .venv folder" rm -rf "$VENV_DIR"
            log_success "The .venv folder was removed."
        fi
    fi

    echo -e "\n${C_GREEN}${C_BOLD}✓ Uninstall complete.${C_RESET}\n"
    exit 0
}

# ------------------------------------------------------------------------------
# 5. Parsing des Arguments
# ------------------------------------------------------------------------------
usage() {
    echo -e "${C_BOLD}Usage:${C_RESET} $0 [options]"
    echo ""
    echo -e "${C_BOLD}Options:${C_RESET}"
    echo -e "  ${C_CYAN}-d, --dry-run${C_RESET}         Dry run: shows the actions without changing the system"
    echo -e "  ${C_CYAN}-v, --venv-only${C_RESET}       Only set up the Python .venv (no apt, no sudo, no systemd)"
    echo -e "  ${C_CYAN}-y, --yes${C_RESET}             Non-interactive: accept the recommended choices automatically"
    echo -e "  ${C_CYAN}-u, --uninstall${C_RESET}       Uninstall the CliOS systemd services and udev rules"
    echo -e "  ${C_CYAN}-h, --help${C_RESET}            Show this help message"
    echo ""
    echo -e "${C_BOLD}Examples:${C_RESET}"
    echo -e "  $0                  # Full interactive installation"
    echo -e "  $0 --dry-run        # Preview without changing anything"
    echo -e "  $0 --venv-only      # Prepare Python / development only"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--dry-run)
            DRY_RUN=1
            shift
            ;;
        -v|--venv-only)
            VENV_ONLY=1
            shift
            ;;
        -y|--yes|--non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        -u|--uninstall)
            DO_UNINSTALL=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

if [[ $DO_UNINSTALL -eq 1 ]]; then
    do_uninstall
fi

# ------------------------------------------------------------------------------
# 6. Début de l'installation
# ------------------------------------------------------------------------------
print_banner

if [[ $DRY_RUN -eq 1 ]]; then
    echo -e "${C_MAGENTA}${C_BOLD}▶ DRY RUN ACTIVE (--dry-run): no changes will be written.${C_RESET}\n"
fi

# ------------------------------------------------------------------------------
# ÉTAPE 1 : Détection de l'Environnement
# ------------------------------------------------------------------------------
log_step "1/6" "Analyzing the system environment"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"
DISTRO="Inconnue"
RELEASE_TARGET=""
EXPECTED_PYTHON_MINOR=""

if [[ "$OS_NAME" == "Linux" ]]; then
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        DISTRO="${PRETTY_NAME:-$NAME}"
    fi
elif [[ "$OS_NAME" == "Darwin" ]]; then
    DISTRO="macOS $(sw_vers -productVersion 2>/dev/null || true)"
fi

if [[ "$OS_NAME" == "Linux" && "$ARCH_NAME" == "aarch64" && -f /etc/debian_version ]]; then
    case "${VERSION_CODENAME:-}" in
        bookworm)
            RELEASE_TARGET="bookworm-arm64"
            EXPECTED_PYTHON_MINOR="3.11"
            ;;
        trixie)
            RELEASE_TARGET="trixie-arm64"
            EXPECTED_PYTHON_MINOR="3.13"
            ;;
        *)
            log_error "Unsupported Debian ARM64 version: ${VERSION_CODENAME:-unknown}. Use Bookworm or Trixie."
            exit 1
            ;;
    esac
fi

log_info "Operating system     : ${C_BOLD}${DISTRO}${C_RESET} (${OS_NAME} ${ARCH_NAME})"
log_info "Target user          : ${C_BOLD}${CURRENT_USER}${C_RESET}"
log_info "Project directory    : ${C_BOLD}${PROJECT_DIR}${C_RESET}"

# Détection de Python 3
find_python_bin() {
    local candidates=()
    if [[ -n "$EXPECTED_PYTHON_MINOR" ]]; then
        candidates+=("/usr/bin/python${EXPECTED_PYTHON_MINOR}" "python${EXPECTED_PYTHON_MINOR}")
    fi
    candidates+=(
        /opt/homebrew/bin/python3.13
        /opt/homebrew/bin/python3.12
        /opt/homebrew/bin/python3.11
        /opt/homebrew/bin/python3
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
        /usr/local/bin/python3.13
        /usr/local/bin/python3.12
        /usr/local/bin/python3.11
        /usr/local/bin/python3
        /usr/bin/python3.13
        /usr/bin/python3.12
        /usr/bin/python3.11
        /usr/bin/python3
        python3.13
        python3.12
        python3.11
        python3
    )
    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" &>/dev/null; then
            local resolved
            resolved="$(command -v "$candidate")"
            if [[ "$resolved" != *"${PROJECT_DIR}/.venv"* ]]; then
                echo "$resolved"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python_bin || true)"

if [[ -n "$PYTHON_BIN" ]]; then
    PY_VER="$($PYTHON_BIN --version 2>&1 | awk '{print $2}')"
    PY_MINOR="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [[ -n "$EXPECTED_PYTHON_MINOR" && "$PY_MINOR" != "$EXPECTED_PYTHON_MINOR" ]]; then
        log_error "${RELEASE_TARGET} requires Python ${EXPECTED_PYTHON_MINOR}, but ${PYTHON_BIN} provides ${PY_MINOR}."
        exit 1
    fi
    log_info "Python binary found  : ${C_BOLD}${PYTHON_BIN}${C_RESET} (version ${PY_VER})"
    if [[ -n "$RELEASE_TARGET" ]]; then
        log_info "Release target       : ${C_BOLD}${RELEASE_TARGET}${C_RESET}"
    fi
    log_success "Environment identified successfully."
else
    if [[ "$OS_NAME" == "Linux" && -f /etc/debian_version && $VENV_ONLY -eq 0 ]]; then
        log_warn "Python 3 is not installed yet. It will be installed in step 2 (APT)."
    else
        log_error "Python 3 was not found. Please install Python 3.11+."
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# ÉTAPE 2 : Dépendances Système (APT)
# ------------------------------------------------------------------------------
log_step "2/6" "System dependencies: C, audio, kiosk display & CAN"

if [[ $VENV_ONLY -eq 1 ]]; then
    log_info "--venv-only active: skipping the system packages step."
elif [[ "$OS_NAME" == "Linux" && -f /etc/debian_version ]]; then
    log_info "Debian / Ubuntu / Raspberry Pi OS distribution detected."
    
    APT_PACKAGES=(
        build-essential
        python3
        python3-dev
        python3-venv
        python3-pip
        portaudio19-dev
        libsndfile1-dev
        liblo-dev
        libjack-jackd2-dev
        libportmidi-dev
        can-utils
        dfu-util
        cage
        seatd
        libgl1
        libegl1
        libxkbcommon0
        libglib2.0-0
        libfontconfig1
        libdbus-1-3
        exfatprogs
        ntfs-3g
    )

    echo -e "\n System packages required for audio (pyo), the CAN bus and Qt / Cage graphics (OpenGL/Wayland):"
    echo -e " ${C_DIM}${APT_PACKAGES[*]}${C_RESET}\n"

    if prompt_confirm "Install / update these system packages with apt?" "Y"; then
        run_sudo_cmd "Updating the apt catalog" apt-get update -y
        run_sudo_cmd "Installing system packages" apt-get install -y "${APT_PACKAGES[@]}"
        log_success "System packages installed."
    else
        log_warn "apt package installation skipped by the user."
    fi

    # Re-détection de Python si absent au départ
    if [[ -z "$PYTHON_BIN" ]]; then
        PYTHON_BIN="$(find_python_bin || true)"
        if [[ -z "$PYTHON_BIN" ]]; then
            if [[ $DRY_RUN -eq 1 ]]; then
                PYTHON_BIN="/usr/bin/python3"
            else
                log_error "Python 3 could not be found after the apt installation."
                exit 1
            fi
        fi
        log_success "Python 3 (${PYTHON_BIN}) working."
    fi
elif [[ "$OS_NAME" == "Darwin" ]]; then
    log_info "macOS detected: apt packages and systemd services do not apply."
    log_info "Python dependencies will be installed for simulation/development mode."
else
    log_warn "Non-Debian system. Make sure you have the C headers for portaudio, liblo, can-utils and cage."
fi

# ------------------------------------------------------------------------------
# ÉTAPE 3 : Environnement Virtuel Python (.venv) & Compilation Pyo
# ------------------------------------------------------------------------------
log_step "3/6" "Python virtual environment (.venv) & dependencies"

if [[ -d "$VENV_DIR" ]]; then
    log_info "A virtual environment already exists in: ${VENV_DIR}"
    if prompt_confirm "Recreate it from scratch (recommended if something is wrong)?" "N"; then
        run_cmd "Removing the old .venv" rm -rf "$VENV_DIR"
        run_cmd "Creating a new .venv environment" "$PYTHON_BIN" -m venv "$VENV_DIR"
        log_success "New virtual environment created."
    else
        log_info "Keeping the existing .venv."
    fi
else
    run_cmd "Creating the .venv virtual environment" "$PYTHON_BIN" -m venv "$VENV_DIR"
    log_success "Virtual environment created in ${VENV_DIR}."
fi

VENV_PYTHON="${VENV_DIR}/bin/python3"
BUNDLED_LOCK="${PROJECT_DIR}/requirements-${RELEASE_TARGET}.lock"
BUNDLED_WHEELS="${PROJECT_DIR}/wheels"

if [[ -n "$RELEASE_TARGET" && -f "$BUNDLED_LOCK" && -d "$BUNDLED_WHEELS" ]] && compgen -G "${BUNDLED_WHEELS}/*.whl" >/dev/null; then
    log_info "Offline installation from the ${RELEASE_TARGET} wheelhouse."
    if [[ $DRY_RUN -eq 1 ]]; then
        log_dry "$VENV_PYTHON -m pip install --no-index --no-deps ${BUNDLED_WHEELS}/*.whl"
        log_dry "$VENV_PYTHON -m pip install --no-index --require-hashes -r $BUNDLED_LOCK"
    else
        "$VENV_PYTHON" -m pip install --no-index --no-deps "${BUNDLED_WHEELS}"/*.whl
        "$VENV_PYTHON" -m pip install --no-index --require-hashes -r "$BUNDLED_LOCK"
        "$VENV_PYTHON" -m pip check
        log_success "${RELEASE_TARGET} wheelhouse installed and verified."
    fi
else
    # Le checkout de développement conserve le chemin PyPI historique. Les
    # archives publiées passent toujours par le wheelhouse ci-dessus.
    run_cmd "Updating pip, setuptools and wheel" "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
    echo -e "\n${C_BOLD}Installing the audio DSP library (pyo)...${C_RESET}"
    BREW_CFLAGS=""
    if [[ "$OS_NAME" == "Darwin" ]]; then
        if [[ -d "/opt/homebrew/include" ]]; then
            BREW_CFLAGS="-I/opt/homebrew/include -L/opt/homebrew/lib"
        elif [[ -d "/usr/local/include" ]]; then
            BREW_CFLAGS="-I/usr/local/include -L/usr/local/lib"
        fi
    fi
    PYO_CFLAGS="${BREW_CFLAGS} -Wno-incompatible-pointer-types -Wno-error"

    if [[ $DRY_RUN -eq 1 ]]; then
        log_dry "CFLAGS=\"${PYO_CFLAGS}\" $VENV_PYTHON -m pip install --no-build-isolation pyo~=1.0.5"
        log_dry "$VENV_PYTHON -m pip install -r ${PROJECT_DIR}/requirements.txt"
    else
        PYO_INSTALLED=0
        if CFLAGS="${PYO_CFLAGS}" "$VENV_PYTHON" -m pip install --no-build-isolation "pyo~=1.0.5" 2>/dev/null; then
            log_success "pyo built and installed successfully."
            PYO_INSTALLED=1
        else
            log_warn "Standard pyo build failed. Retrying without OSC..."
            if CFLAGS="${PYO_CFLAGS}" "$VENV_PYTHON" -m pip install --no-binary :all: --config-settings="--build-option=--no-osc" "pyo~=1.0.5" 2>/dev/null; then
                log_success "pyo installed successfully (fallback mode without OSC)."
                PYO_INSTALLED=1
            else
                log_warn "pyo could not be built (audio C headers missing). Engine sound features will be disabled."
            fi
        fi
        log_info "Installing dependencies from requirements.txt..."
        if [[ $PYO_INSTALLED -eq 1 ]]; then
            "$VENV_PYTHON" -m pip install -r "${PROJECT_DIR}/requirements.txt"
        else
            grep -v '^pyo' "${PROJECT_DIR}/requirements.txt" | "$VENV_PYTHON" -m pip install -r /dev/stdin
        fi
        log_success "Python dependencies installed."
    fi
fi

if [[ $DRY_RUN -eq 0 ]]; then
    log_info "Validating critical Python modules..."
    if "$VENV_PYTHON" -c "import PySide6; print(f'PySide6 version: {PySide6.__version__}')" &>/dev/null; then
        log_success "PySide6 working."
    else
        log_warn "PySide6 could not be validated in the quick test."
    fi

    if "$VENV_PYTHON" -c "import pyo; print(f'pyo version: {pyo.PYO_VERSION}')" &>/dev/null; then
        log_success "pyo audio working."
    else
        log_info "pyo audio disabled (normal in simulation on a Mac without portaudio headers)."
    fi
fi

# ------------------------------------------------------------------------------
# ÉTAPE 4 : Configuration Matérielle CAN & Udev
# ------------------------------------------------------------------------------
log_step "4/6" "CAN hardware & udev rules"

if [[ $VENV_ONLY -eq 1 || "$OS_NAME" != "Linux" ]]; then
    log_info "CAN step skipped (venv-only mode or non-Linux system)."
else
    echo -e "Select your CAN adapter type to configure the system services:"
    echo -e "  ${C_CYAN}1)${C_RESET} ${C_BOLD}Native Candlelight / CAN-USB adapter${C_RESET} (enables can-usb.service)"
    echo -e "  ${C_CYAN}2)${C_RESET} ${C_BOLD}SLCAN USB adapter (/dev/ttyACM0)${C_RESET}   (enables slcan.service + udev rule)"
    echo -e "  ${C_CYAN}3)${C_RESET} ${C_BOLD}STM32 DFU wake-up only${C_RESET}           (enables can-wake.service)"
    echo -e "  ${C_CYAN}4)${C_RESET} ${C_BOLD}Native + STM32 DFU wake-up${C_RESET}       (can-usb.service + can-wake.service)"
    echo -e "  ${C_CYAN}5)${C_RESET} ${C_BOLD}Change nothing / Simulation mode${C_RESET} [Recommended if already configured]"

    CHOICE="5"
    if [[ $NON_INTERACTIVE -eq 0 ]]; then
        read -r -p "$(echo -e "\n${C_BOLD}Your choice [1-5] (default: 5): ${C_RESET}")" input_choice
        CHOICE="${input_choice:-5}"
    fi

    run_sudo_cmd "Creating system directories" mkdir -p "${SYSTEMD_DIR}" "${UDEV_RULES_DIR}"

    case "$CHOICE" in
        1)
            log_info "Configuring the native Candlelight adapter (can-usb.service)..."
            backup_system_file "${SYSTEMD_DIR}/can-usb.service"
            run_sudo_cmd "Copying can-usb.service" cp "${INSTALL_ETC_DIR}/systemd/system/can-usb.service" "${SYSTEMD_DIR}/"
            safe_systemctl "Reloading the systemd daemon" daemon-reload
            safe_systemctl "Enabling can-usb.service" enable can-usb.service
            log_success "can-usb service configured and enabled."
            ;;
        2)
            log_info "Configuring the SLCAN adapter (/dev/ttyACM0)..."
            backup_system_file "${SYSTEMD_DIR}/slcan.service"
            backup_system_file "${UDEV_RULES_DIR}/99-slcan.rules"
            run_sudo_cmd "Copying slcan.service" cp "${INSTALL_ETC_DIR}/systemd/system/slcan.service" "${SYSTEMD_DIR}/"
            run_sudo_cmd "Copying 99-slcan.rules" cp "${INSTALL_ETC_DIR}/udev/rules.d/99-slcan.rules" "${UDEV_RULES_DIR}/"
            safe_systemctl "Reloading systemd" daemon-reload
            safe_udevadm "Reloading udev rules" control --reload-rules
            safe_udevadm "Applying udev rules" trigger
            safe_systemctl "Enabling slcan.service" enable slcan.service
            log_success "SLCAN service and udev rules configured."
            ;;
        3)
            log_info "Configuring STM32 DFU wake-up..."
            backup_system_file "${SYSTEMD_DIR}/can-wake.service"
            run_sudo_cmd "Copying can-wake.service" cp "${INSTALL_ETC_DIR}/systemd/system/can-wake.service" "${SYSTEMD_DIR}/"
            safe_systemctl "Reloading systemd" daemon-reload
            safe_systemctl "Enabling can-wake.service" enable can-wake.service
            log_success "can-wake service configured."
            ;;
        4)
            log_info "Configuring native + DFU wake-up..."
            backup_system_file "${SYSTEMD_DIR}/can-usb.service"
            backup_system_file "${SYSTEMD_DIR}/can-wake.service"
            run_sudo_cmd "Copying can-usb.service" cp "${INSTALL_ETC_DIR}/systemd/system/can-usb.service" "${SYSTEMD_DIR}/"
            run_sudo_cmd "Copying can-wake.service" cp "${INSTALL_ETC_DIR}/systemd/system/can-wake.service" "${SYSTEMD_DIR}/"
            safe_systemctl "Reloading systemd" daemon-reload
            safe_systemctl "Enabling can-usb.service" enable can-usb.service
            safe_systemctl "Enabling can-wake.service" enable can-wake.service
            log_success "can-usb and can-wake services configured."
            ;;
        *)
            log_info "No changes made to the CAN hardware services."
            ;;
    esac
fi

# ------------------------------------------------------------------------------
# ÉTAPE 5 : Démarrage Automatique Kiosk (Wayland / Cage clios.service)
# ------------------------------------------------------------------------------
log_step "5/6" "Automatic start at boot (standalone kiosk via Cage)"

if [[ $VENV_ONLY -eq 1 || "$OS_NAME" != "Linux" ]]; then
    log_info "Kiosk autostart step skipped (venv-only mode or non-Linux system)."
else
    echo -e "CliOS can start automatically in full screen at boot using the ${C_BOLD}Cage${C_RESET} Wayland compositor (no desktop needed)."
    if prompt_confirm "Install the kiosk startup service (clios.service)?" "N"; then
        KIOSK_INSTALLED=1
        if ! getent group clios >/dev/null 2>&1; then
            run_sudo_cmd "Creating the clios system group" groupadd --system clios
        fi
        if ! id clios >/dev/null 2>&1; then
            run_sudo_cmd "Creating the clios self-check user" useradd --system --gid clios --home-dir /var/lib/clios --shell /usr/sbin/nologin clios
        fi
        run_sudo_cmd "Giving ${CURRENT_USER} access to the updater socket" usermod -a -G clios "${CURRENT_USER}"
        RELEASE_VERSION="$(tr -d '[:space:]' < "${PROJECT_DIR}/VERSION")"
        RELEASE_DIR="/opt/clios/releases/${RELEASE_VERSION}"
        run_sudo_cmd "Creating release directories" mkdir -p "$(dirname "$RELEASE_DIR")" /var/lib/clios /run/clios
        if [[ $DRY_RUN -eq 1 ]]; then
            log_dry "Staging ${PROJECT_DIR} without .venv, moving the .venv, then linking /opt/clios/current"
        else
            safe_systemctl "Stopping CliOS before replacing the release" stop clios.service 2>/dev/null || true
            install_release_tree "$RELEASE_DIR"
            run_sudo_cmd "Initial release activation" ln -sfn "${RELEASE_DIR}" /opt/clios/current
            for legacy_dir in dash_save trips trips_mock logs; do
                if [[ -d "${PROJECT_DIR}/data/${legacy_dir}" ]]; then
                    run_sudo_cmd "Preparing storage ${legacy_dir}" mkdir -p "/var/lib/clios/${legacy_dir}"
                    run_sudo_cmd "Non-destructive migration of ${legacy_dir}" cp -an "${PROJECT_DIR}/data/${legacy_dir}/." "/var/lib/clios/${legacy_dir}/"
                fi
            done
        fi

        USER_UID="$(id -u "$CURRENT_USER" 2>/dev/null || echo 1000)"
        TMP_SERVICE_FILE="/tmp/clios.service"
        python3 "${PROJECT_DIR}/tools/generate_systemd.py" \
            --user "${CURRENT_USER}" --uid "${USER_UID}" --output "${TMP_SERVICE_FILE}"

        run_sudo_cmd "Creating system directories" mkdir -p "${SYSTEMD_DIR}" "${UDEV_RULES_DIR}" "${LOCAL_LIBEXEC_DIR}" "${SUDOERS_DIR}" /etc/clios /var/lib/clios /run/clios /media/clios
        run_sudo_cmd "Creating the Polkit directory" mkdir -p "${POLKIT_RULES_DIR}"
        run_sudo_cmd "Updater data ownership" chown root:clios /var/lib/clios /run/clios
        run_sudo_cmd "Updater data permissions" chmod 0770 /var/lib/clios /run/clios
        backup_system_file "${SYSTEMD_DIR}/clios.service"
        backup_system_file "${SYSTEMD_DIR}/clios-updater.service"
        backup_system_file "${SYSTEMD_DIR}/clios-updater.socket"
        backup_system_file "${SYSTEMD_DIR}/clios-usb-mount@.service"
        backup_system_file "${UDEV_RULES_DIR}/90-clios-usb-storage.rules"
        backup_system_file "${LOCAL_LIBEXEC_DIR}/clios-usb-mount"
        backup_system_file "/etc/clios/updater.json"
        backup_system_file "/etc/clios/release-keys.json"
        backup_system_file "${POLKIT_RULES_DIR}/49-clios-power.rules"
        backup_system_file "${SUDOERS_DIR}/clios-overlayfs"

        if [[ $DRY_RUN -eq 1 ]]; then
            log_dry "Generated service content (${TMP_SERVICE_FILE}):"
            cat "$TMP_SERVICE_FILE"
        else
            run_sudo_cmd "Installing clios.service" cp "$TMP_SERVICE_FILE" "${SYSTEMD_DIR}/clios.service"
            run_sudo_cmd "Setting permissions on clios.service" chmod 644 "${SYSTEMD_DIR}/clios.service"
            run_sudo_cmd "Installing clios-updater.service" cp "${INSTALL_ETC_DIR}/systemd/system/clios-updater.service" "${SYSTEMD_DIR}/clios-updater.service"
            run_sudo_cmd "Installing clios-updater.socket" cp "${INSTALL_ETC_DIR}/systemd/system/clios-updater.socket" "${SYSTEMD_DIR}/clios-updater.socket"
            run_sudo_cmd "Installing the USB mount service" cp "${INSTALL_ETC_DIR}/systemd/system/clios-usb-mount@.service" "${SYSTEMD_DIR}/clios-usb-mount@.service"
            run_sudo_cmd "Installing the USB storage rule" cp "${INSTALL_ETC_DIR}/udev/rules.d/90-clios-usb-storage.rules" "${UDEV_RULES_DIR}/90-clios-usb-storage.rules"
            run_sudo_cmd "Installing the USB mount helper" cp "${PROJECT_DIR}/installation/usr/local/libexec/clios-usb-mount" "${LOCAL_LIBEXEC_DIR}/clios-usb-mount"
            run_sudo_cmd "USB mount helper permissions" chmod 0755 "${LOCAL_LIBEXEC_DIR}/clios-usb-mount"
            run_sudo_cmd "Installing the updater trust source" cp "${INSTALL_ETC_DIR}/clios/updater.json" /etc/clios/updater.json
            run_sudo_cmd "Updater trust source ownership" chown root:root /etc/clios/updater.json
            run_sudo_cmd "Updater trust source permissions" chmod 0644 /etc/clios/updater.json
            run_sudo_cmd "Installing the publishing keyring" cp "${INSTALL_ETC_DIR}/clios/release-keys.json" /etc/clios/release-keys.json
            run_sudo_cmd "Publishing keyring ownership" chown root:root /etc/clios/release-keys.json
            run_sudo_cmd "Publishing keyring permissions" chmod 0644 /etc/clios/release-keys.json
            sed "s/@CLIOS_USER@/${CURRENT_USER}/g" \
                "${INSTALL_ETC_DIR}/polkit-1/rules.d/49-clios-power.rules.in" > /tmp/49-clios-power.rules
            run_sudo_cmd "Installing the CliOS Polkit rule" cp /tmp/49-clios-power.rules "${POLKIT_RULES_DIR}/49-clios-power.rules"
            run_sudo_cmd "CliOS Polkit rule permissions" chmod 0644 "${POLKIT_RULES_DIR}/49-clios-power.rules"
            rm -f /tmp/49-clios-power.rules
            sed "s/@CLIOS_USER@/${CURRENT_USER}/g" \
                "${INSTALL_ETC_DIR}/sudoers.d/clios-overlayfs.in" > /tmp/clios-overlayfs.sudoers
            run_sudo_cmd "Validating the OverlayFS permission" visudo -cf /tmp/clios-overlayfs.sudoers
            run_sudo_cmd "Installing the OverlayFS permission" cp /tmp/clios-overlayfs.sudoers "${SUDOERS_DIR}/clios-overlayfs"
            run_sudo_cmd "OverlayFS permission file mode" chmod 0440 "${SUDOERS_DIR}/clios-overlayfs"
            rm -f /tmp/clios-overlayfs.sudoers
            safe_systemctl "Reloading the systemd daemon" daemon-reload
            safe_udevadm "Reloading USB storage rules" control --reload-rules
            safe_udevadm "Detecting USB storage already plugged in" trigger --subsystem-match=block --action=add
            safe_systemctl "Enabling the updater socket" enable --now clios-updater.socket
            rm -f "$TMP_SERVICE_FILE"

            if prompt_confirm "Enable CliOS to start automatically at every boot now?" "Y"; then
                safe_systemctl "Enabling clios.service" enable clios.service
                KIOSK_AUTOSTART_ENABLED=1
                log_success "clios.service configured to start with the system."
            else
                log_info "clios.service installed but not enabled (use 'sudo systemctl enable clios.service' later)."
            fi
        fi
        log_success "Kiosk service configuration complete."
    else
        log_info "Kiosk service installation skipped."
    fi
fi

# ------------------------------------------------------------------------------
# ÉTAPE 6 : Optimisations Fast-Boot pour Raspberry Pi
# ------------------------------------------------------------------------------
log_step "6/6" "Fast-boot optimizations"

if [[ $VENV_ONLY -eq 1 || "$OS_NAME" != "Linux" ]]; then
    log_info "Fast-boot step skipped (venv-only mode or non-Linux system)."
else
    echo -e "Careful boot speed-up that keeps networking, BLE, USB, CAN and the updater enabled."
    echo -e "Each sensitive group is confirmed separately and stays reversible."
    if prompt_confirm "Disable these slow services at boot?" "N"; then
        SLOW_SERVICES=(
            NetworkManager-wait-online.service
            apt-daily.timer
            apt-daily-upgrade.timer
            man-db.timer
            dphys-swapfile.service
            rpi-eeprom-update.service
        )
        for srv in "${SLOW_SERVICES[@]}"; do
            disable_systemd_unit_if_present "${srv}"
        done
        FAST_BOOT_APPLIED+=("non-essential background services")
        log_success "Slow services disabled successfully."
    else
        FAST_BOOT_SKIPPED+=("non-essential background services")
        log_info "Skipped disabling background services."
    fi

    KIOSK_UNIT_AVAILABLE=0
    if [[ $KIOSK_INSTALLED -eq 1 ]] || systemd_unit_exists clios.service; then
        KIOSK_UNIT_AVAILABLE=1
    fi
    if [[ $KIOSK_UNIT_AVAILABLE -eq 1 ]]; then
        echo -e "\nThe CliOS kiosk mode does not need LightDM. The change takes effect at the next boot."
        if prompt_confirm "Disable LightDM and boot to multi-user.target by default?" "N"; then
            disable_systemd_unit_if_present lightdm.service
            safe_systemctl "Selecting desktop-free kiosk boot" set-default multi-user.target
            FAST_BOOT_APPLIED+=("kiosk mode without LightDM")
            log_success "Kiosk mode configured without stopping the current graphical session."
        else
            FAST_BOOT_SKIPPED+=("kiosk mode without LightDM")
            log_info "LightDM and the default target are unchanged."
        fi
    else
        FAST_BOOT_SKIPPED+=("kiosk mode without LightDM (CliOS not installed)")
        log_info "LightDM optimization not offered: clios.service is not installed."
    fi

    echo -e "\n${C_YELLOW}${C_BOLD}Only disable cloud-init after initial provisioning.${C_RESET}"
    echo -e "This keeps its configuration but stops its units from slowing down future boots."
    if prompt_confirm "Is this machine provisioned, and can cloud-init be disabled?" "N"; then
        if [[ -e /etc/cloud/cloud-init.disabled ]]; then
            log_info "cloud-init is already disabled."
        else
            run_sudo_cmd "Reversibly disabling cloud-init" mkdir -p /etc/cloud
            run_sudo_cmd "Creating the cloud-init.disabled marker" touch /etc/cloud/cloud-init.disabled
        fi
        FAST_BOOT_APPLIED+=("cloud-init disabled")
        log_success "cloud-init will be skipped at the next boots."
    else
        FAST_BOOT_SKIPPED+=("cloud-init kept")
        log_info "cloud-init stays enabled."
    fi

    echo -e "\n ${C_CYAN}ℹ${C_RESET} ${C_BOLD}Hardware tip:${C_RESET} check the EEPROM and config.txt with"
    echo -e "   ${C_CYAN}installation/guide_optimisation_boot_rpi5.md${C_RESET}, without adding untested overclocking."
fi

# ------------------------------------------------------------------------------
# Rendu Final & Instructions d'utilisation
# ------------------------------------------------------------------------------
echo -e "\n${C_GREEN}${C_BOLD}══════════════════════════════════════════════════════════════════${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}  ✓ CliOS INSTALLATION COMPLETED SUCCESSFULLY!${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}══════════════════════════════════════════════════════════════════${C_RESET}\n"

if [[ $KIOSK_INSTALLED -eq 1 ]]; then
    echo -e "${C_BOLD}CliOS is installed in /opt/clios/current.${C_RESET}\n"
    echo -e "  ${C_CYAN}sudo systemctl start clios.service${C_RESET}    # Start the cockpit now"
    echo -e "  ${C_CYAN}sudo systemctl status clios.service${C_RESET}   # Check its status"
    echo -e "  ${C_CYAN}journalctl -u clios.service -f${C_RESET}        # Follow the logs"
    echo -e "  ${C_DIM}./clios --help automatically redirects to /opt/clios/current.${C_RESET}\n"
    if [[ $KIOSK_AUTOSTART_ENABLED -eq 1 ]] && prompt_confirm "Start CliOS now?" "Y"; then
        safe_systemctl "Starting CliOS now" start clios.service
    fi
else
    echo -e "${C_BOLD}You can now start CliOS from this folder:${C_RESET}\n"
    echo -e "  ${C_CYAN}./clios${C_RESET}                 # Standard launch"
    echo -e "  ${C_CYAN}./clios --mock${C_RESET}          # Simulation without hardware"
    echo -e "  ${C_CYAN}./clios --ui cli --mock${C_RESET} # Interactive terminal"
    echo -e "  ${C_CYAN}./clios --help${C_RESET}          # Available options\n"
fi

if [[ ${#FAST_BOOT_APPLIED[@]} -gt 0 ]]; then
    log_success "Fast-boot applied: ${FAST_BOOT_APPLIED[*]}"
fi
if [[ ${#FAST_BOOT_SKIPPED[@]} -gt 0 ]]; then
    log_info "Fast-boot not applied: ${FAST_BOOT_SKIPPED[*]}"
fi
if [[ ${#FAST_BOOT_APPLIED[@]} -gt 0 ]]; then
    echo -e "\n${C_BOLD}Reverting the fast-boot optimizations:${C_RESET}"
    echo -e "  ${C_CYAN}sudo systemctl set-default graphical.target${C_RESET}"
    echo -e "  ${C_CYAN}sudo systemctl enable lightdm.service NetworkManager-wait-online.service${C_RESET}"
    echo -e "  ${C_CYAN}sudo rm -f /etc/cloud/cloud-init.disabled${C_RESET}"
fi
