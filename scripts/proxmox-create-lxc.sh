#!/usr/bin/env bash
#
# Create a Proxmox LXC container and install the Live Nation onsale monitor
# into it. RUN THIS ON THE PROXMOX VE HOST (not inside a container).
#
#     bash scripts/proxmox-create-lxc.sh
#
# It will:
#   1. pick the next free container ID (or use $CTID)
#   2. download a Debian 12 template if one isn't present
#   3. create an unprivileged container (DHCP networking)
#   4. copy this repo in and run scripts/install.sh inside it
#
# Everything is configurable via environment variables (defaults shown):
#   CTID=<next free id>   HOSTNAME=ticketbot   STORAGE=local-lvm   BRIDGE=vmbr0
#   MEMORY=512 (MB)       CORES=1              DISK=4 (GB)         TEMPLATE_STORAGE=local
#   CT_PASSWORD=<random>  ASSUME_YES=0
set -euo pipefail

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

command -v pct >/dev/null 2>&1 || die "pct not found -- run this on the Proxmox VE host"
command -v pveam >/dev/null 2>&1 || die "pveam not found -- run this on the Proxmox VE host"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "${REPO_ROOT}/scripts/install.sh" ] || die "scripts/install.sh missing; run from a repo checkout"

CTID="${CTID:-$(pvesh get /cluster/nextid)}"
HOSTNAME="${HOSTNAME:-ticketbot}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
MEMORY="${MEMORY:-512}"
CORES="${CORES:-1}"
DISK="${DISK:-4}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
CT_PASSWORD="${CT_PASSWORD:-$(openssl rand -base64 12 2>/dev/null || echo ChangeMe123!)}"
ASSUME_YES="${ASSUME_YES:-0}"

# Find a Debian 12 template, downloading it if necessary.
log "Locating a Debian 12 LXC template"
pveam update >/dev/null 2>&1 || true
TEMPLATE_FILE="$(pveam list "${TEMPLATE_STORAGE}" 2>/dev/null | awk '/debian-12-standard/ {print $1}' | head -n1 || true)"
if [ -z "${TEMPLATE_FILE}" ]; then
    AVAIL="$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort | tail -n1)"
    [ -n "${AVAIL}" ] || die "no debian-12-standard template available via pveam"
    log "Downloading template ${AVAIL} to ${TEMPLATE_STORAGE}"
    pveam download "${TEMPLATE_STORAGE}" "${AVAIL}"
    TEMPLATE_FILE="${TEMPLATE_STORAGE}:vztmpl/${AVAIL}"
fi

cat <<EOF

About to create a Proxmox LXC:
  Container ID : ${CTID}
  Hostname     : ${HOSTNAME}
  Template     : ${TEMPLATE_FILE}
  Resources    : ${CORES} core(s), ${MEMORY} MB RAM, ${DISK} GB disk on ${STORAGE}
  Network      : ${BRIDGE} (DHCP), unprivileged, nesting enabled, start on boot
EOF
if [ "${ASSUME_YES}" != "1" ]; then
    read -r -p "Proceed? [y/N] " reply
    case "${reply}" in y|Y|yes|YES) ;; *) die "aborted by user" ;; esac
fi

log "Creating container ${CTID}"
pct create "${CTID}" "${TEMPLATE_FILE}" \
    --hostname "${HOSTNAME}" \
    --cores "${CORES}" \
    --memory "${MEMORY}" \
    --swap "${MEMORY}" \
    --rootfs "${STORAGE}:${DISK}" \
    --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
    --unprivileged 1 \
    --features nesting=1 \
    --onboot 1 \
    --password "${CT_PASSWORD}"

log "Starting container ${CTID}"
pct start "${CTID}"

log "Waiting for network inside the container"
for _ in $(seq 1 30); do
    if pct exec "${CTID}" -- getent hosts api.telegram.org >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

log "Copying application into the container"
TARBALL="$(mktemp /tmp/ticketbot.XXXXXX.tgz)"
trap 'rm -f "${TARBALL}"' EXIT
tar czf "${TARBALL}" -C "${REPO_ROOT}" \
    ticketbot run.py requirements.txt deploy scripts config.example.yaml .env.example README.md
pct exec "${CTID}" -- mkdir -p /opt/ticketbot-src
pct push "${CTID}" "${TARBALL}" /opt/ticketbot-src/ticketbot.tgz
pct exec "${CTID}" -- tar xzf /opt/ticketbot-src/ticketbot.tgz -C /opt/ticketbot-src

log "Running the installer inside the container"
pct exec "${CTID}" -- bash /opt/ticketbot-src/scripts/install.sh

cat <<EOF

$(log "Container ${CTID} (${HOSTNAME}) is ready.")
  Root password: ${CT_PASSWORD}

Finish setup inside the container:
  pct enter ${CTID}
  nano /etc/ticketbot/.env          # add TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  nano /etc/ticketbot/config.yaml   # add your event URL(s)
  systemctl start ticketbot.service
  journalctl -u ticketbot.service -f
EOF
