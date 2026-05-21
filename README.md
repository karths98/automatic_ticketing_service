# automatic_ticketing_service

A polite **onsale monitor** for [Live Nation Malaysia](https://www.livenation.my) that
pings you on **Telegram** with a direct link the moment a show you're watching goes on sale.
You then jump into the queue and complete payment yourself.

## What this does — and what it deliberately does not do

- ✅ Watches a public event page on a sensible interval.
- ✅ Detects when tickets transition to **on sale** (or, if you prefer, sold-out / not-yet).
- ✅ Sends a Telegram message with the event link so you can act fast.
- ❌ Does **not** join the Queue-it waiting room for you.
- ❌ Does **not** solve CAPTCHAs, fake a browser, or evade bot detection.
- ❌ Does **not** add tickets to a cart or pay on your behalf.

Automated ticket-buying bots violate Live Nation / Ticketmaster's Terms of Service and are
illegal in many places (e.g. the US BOTS Act). This tool stays firmly on the right side of
that line: it only watches and alerts. A human still does the buying.

## How it detects onsale status

Live Nation Malaysia event pages are server-rendered and embed the event's sale schedule
directly in the page payload — `waitroomOpenUtc` (when the waiting room / queue opens) and
`validFromUtc` (when tickets actually go on sale). Comparing those timestamps to the current
time is the primary, ground-truth signal (verified against live event pages).

Because Live Nation runs a **waiting room that opens before onsale** (you must be in the queue
*before* tickets release), the bot treats the **waiting-room-open moment as the "go" signal** —
that's when it alerts you, with a message telling you to join the queue and the exact onsale
time. This matches the real flow: queue first, buy when the window opens.

If a page ever lacks those timestamps, detection falls back to [schema.org](https://schema.org/Event)
`offers.availability` JSON-LD, and finally to a configurable keyword scan of the visible text.

## Setup

### 1. Install

```bash
pip install -r requirements.txt
```

(Python 3.10+.)

### 2. Create your Telegram bot and get your chat id

1. In Telegram, open a chat with **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot` and follow the prompts. BotFather gives you a **bot token** that looks like
   `123456789:ABCdef...`.
3. **Send any message** (e.g. "hi") to your new bot — this lets the bot see your chat.
4. Find your **chat id**: open this URL in a browser, replacing `<TOKEN>`:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Look for `"chat":{"id":123456789,...}` — that number is your `TELEGRAM_CHAT_ID`.

### 3. Configure

```bash
cp .env.example .env                # then edit: paste your token and chat id
cp config.example.yaml config.yaml  # then edit: paste your event URL(s)
```

`.env`:
```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=123456789
```

`config.yaml` (one entry per event you want to watch):
```yaml
poll_interval_seconds: 60
events:
  - name: "Coldplay - Kuala Lumpur"
    url: "https://www.livenation.my/event/REAL-EVENT-ID"
    watch_for: on_sale   # on_sale | not_yet | sold_out
```

### 4. Verify Telegram works

```bash
python run.py test-telegram
```

You should receive a "connected" message in your Telegram chat.

## Usage

```bash
# Run a single check (great for cron):
python run.py check-once

# Watch continuously until every event has alerted (Ctrl-C to stop):
python run.py run
```

You'll get one Telegram alert per event when it hits the status you're watching for. The bot
remembers what it's already alerted (in `state.json`) so it won't spam you.

### Running it somewhere persistent

This needs to keep running to be useful, so run it on a machine that stays on — your own
computer, a Raspberry Pi, a small VPS, or a **Proxmox LXC** (see below). For a quick-and-dirty
run you can use `python run.py run` under `tmux`/`nohup`, but the supported deployment is the
systemd service installed by `scripts/install.sh`.

> Keep `poll_interval_seconds` reasonable (30–120s). Polling faster won't get you tickets any
> sooner — the queue is what gates purchases — and it's rude to the site.

## Run as a Proxmox LXC

The tool ships with a systemd unit (`deploy/ticketbot.service`) and two install scripts.

### Option A — let the script create the container for you (run on the Proxmox host)

From a checkout of this repo **on your Proxmox VE node**:

```bash
bash scripts/proxmox-create-lxc.sh
```

This picks the next free container ID, downloads a Debian 12 template if needed, creates an
unprivileged LXC (DHCP, 1 core / 512 MB / 4 GB by default), copies the app in, and runs the
installer inside it. Override any default via environment variables, e.g.:

```bash
CTID=210 HOSTNAME=ticketbot MEMORY=512 DISK=4 STORAGE=local-lvm BRIDGE=vmbr0 \
  bash scripts/proxmox-create-lxc.sh
```

When it finishes it prints the container's root password and the remaining steps.

### Option B — install into an LXC you already created

Create a Debian/Ubuntu LXC yourself (Proxmox UI → Create CT), then inside it:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/karths98/automatic_ticketing_service.git
cd automatic_ticketing_service
bash scripts/install.sh
```

### After installing (either option)

The installer creates a `ticketbot` system user and lays things out like this:

| Path | Purpose |
|------|---------|
| `/opt/ticketbot` | application code + Python virtualenv |
| `/etc/ticketbot/.env` | Telegram token + chat id (mode 600) |
| `/etc/ticketbot/config.yaml` | events to watch + poll settings |
| `/var/lib/ticketbot/state.json` | which events have already alerted |

Finish setup:

```bash
nano /etc/ticketbot/.env          # add TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
nano /etc/ticketbot/config.yaml   # add your event URL(s)

# verify Telegram works:
sudo -u ticketbot /opt/ticketbot/.venv/bin/python /opt/ticketbot/run.py \
  --env-file /etc/ticketbot/.env test-telegram

systemctl start ticketbot.service
systemctl status ticketbot.service
journalctl -u ticketbot.service -f   # live logs
```

The service is enabled on boot and restarts on failure. It runs until every watched event has
fired its one alert, then exits cleanly; add more events to `config.yaml` and
`systemctl restart ticketbot` to watch them. Re-running `scripts/install.sh` updates the code
and dependencies while preserving your config, secrets, and state.

## Run the tests

No external test framework needed — uses the standard library:

```bash
python -m unittest discover -s tests -v
```

## Project layout

```
ticketbot/
  config.py    # YAML config + env-based secrets
  fetcher.py   # polite HTTP GET of the event page
  detector.py  # JSON-LD + keyword onsale detection
  notifier.py  # Telegram Bot API messages
  state.py     # remembers what's already been alerted
  monitor.py   # the poll -> detect -> notify loop
  cli.py       # `run` / `check-once` / `test-telegram`
run.py         # entrypoint
deploy/
  ticketbot.service        # systemd unit
scripts/
  install.sh               # install as a systemd service (run inside the LXC)
  proxmox-create-lxc.sh    # create the LXC + install (run on the Proxmox host)
```
