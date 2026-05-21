#!/usr/bin/env bash
#
# Install the Live Nation onsale monitor as a systemd service.
#
# Run this *inside* a Debian/Ubuntu LXC (or any systemd host) as root, from a
# checked-out copy of this repo:
#
#     git clone <repo> /root/automatic_ticketing_service
#     cd /root/automatic_ticketing_service
#     sudo bash scripts/install.sh
#
# It is idempotent: re-running updates the code and dependencies while leaving
# your /etc/ticketbot/config.yaml, /etc/ticketbot/.env and state untouched.
set -euo pipefail

APP_USER="ticketbot"
APP_DIR="/opt/ticketbot"
CONF_DIR="/etc/ticketbot"
STATE_DIR="/var/lib/ticketbot"
VENV="${APP_DIR}/.venv"
UNIT="/etc/systemd/system/ticketbot.service"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "please run as root (e.g. sudo bash scripts/install.sh)"
[ -f "${REPO_ROOT}/run.py" ] || die "run.py not found; run this from a checkout of the repo"

log "Installing system packages (python3, venv, pip)"
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip ca-certificates >/dev/null
else
    command -v python3 >/dev/null 2>&1 || die "python3 not found and no apt-get to install it"
fi

log "Creating service user '${APP_USER}'"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --home-dir "${STATE_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

log "Creating directories"
mkdir -p "${APP_DIR}" "${CONF_DIR}" "${STATE_DIR}"

log "Copying application code to ${APP_DIR}"
cp -a "${REPO_ROOT}/ticketbot" "${APP_DIR}/"
cp -a "${REPO_ROOT}/run.py" "${REPO_ROOT}/requirements.txt" "${APP_DIR}/"

log "Creating Python virtualenv and installing dependencies"
[ -d "${VENV}" ] || python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade --quiet pip
"${VENV}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

log "Installing config files (existing ones are preserved)"
if [ ! -f "${CONF_DIR}/config.yaml" ]; then
    cp "${REPO_ROOT}/config.example.yaml" "${CONF_DIR}/config.yaml"
    NEW_CONFIG=1
fi
if [ ! -f "${CONF_DIR}/.env" ]; then
    cp "${REPO_ROOT}/.env.example" "${CONF_DIR}/.env"
    NEW_CONFIG=1
fi
chmod 600 "${CONF_DIR}/.env"

log "Setting ownership"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" "${CONF_DIR}" "${STATE_DIR}"

log "Installing systemd unit"
cp "${REPO_ROOT}/deploy/ticketbot.service" "${UNIT}"
systemctl daemon-reload
systemctl enable ticketbot.service >/dev/null 2>&1 || true

cat <<EOF

$(log "Done.")
Next steps:
  1. Edit your Telegram credentials:   ${CONF_DIR}/.env
     (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID -- see the README for how to get them)
  2. Edit the event(s) to watch:        ${CONF_DIR}/config.yaml
  3. Verify Telegram works:
       sudo -u ${APP_USER} ${VENV}/bin/python ${APP_DIR}/run.py --env-file ${CONF_DIR}/.env test-telegram
  4. Start the monitor:
       systemctl start ticketbot.service
       systemctl status ticketbot.service
       journalctl -u ticketbot.service -f      # live logs

The service is enabled, so it will also start automatically on boot.
EOF

if [ "${NEW_CONFIG:-0}" = "1" ]; then
    echo
    echo "NOTE: the service will fail to start until you fill in ${CONF_DIR}/.env"
fi
