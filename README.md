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
computer, a Raspberry Pi, or a small VPS. Two common patterns:

- **Continuous:** `python run.py run` under `tmux`/`systemd`/`nohup`.
- **Cron:** `*/2 * * * * cd /path/to/repo && python run.py check-once` (every 2 minutes).

> Keep `poll_interval_seconds` reasonable (30–120s). Polling faster won't get you tickets any
> sooner — the queue is what gates purchases — and it's rude to the site.

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
```
