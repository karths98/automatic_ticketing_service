#!/usr/bin/env python3
"""Thin entrypoint so you can run `python run.py <command>`."""

from ticketbot.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
