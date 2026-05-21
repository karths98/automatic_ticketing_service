"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config, load_dotenv, load_telegram_config
from .monitor import Monitor
from .notifier import NotifyError, TelegramNotifier
from .state import AlertState


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_monitor(config_path: str) -> Monitor:
    config = load_config(config_path)
    telegram = load_telegram_config()
    notifier = TelegramNotifier(telegram)
    return Monitor(config, notifier, AlertState(config.state_file))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ticketbot",
        description=(
            "Watch Live Nation event pages and alert you on Telegram the moment "
            "tickets go on sale. It never joins the queue or buys for you."
        ),
    )
    parser.add_argument(
        "--env-file", default=".env", help="path to a .env file (default: .env)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="poll continuously until every event has alerted")
    p_run.add_argument("--config", default="config.yaml", help="path to config.yaml")

    p_once = sub.add_parser("check-once", help="run a single pass and exit (good for cron)")
    p_once.add_argument("--config", default="config.yaml", help="path to config.yaml")

    sub.add_parser("test-telegram", help="send a test message to verify Telegram setup")

    args = parser.parse_args(argv)
    _setup_logging()
    load_dotenv(args.env_file)

    try:
        if args.command == "test-telegram":
            notifier = TelegramNotifier(load_telegram_config())
            notifier.test_connection()
            print("Test message sent. Check your Telegram chat.")
            return 0

        monitor = _build_monitor(args.config)
        if args.command == "check-once":
            monitor.check_all()
            return 0
        if args.command == "run":
            monitor.run_forever()
            return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except (ValueError, FileNotFoundError, NotifyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
