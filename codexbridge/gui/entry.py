from __future__ import annotations

import argparse

from codexbridge.service import run_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CodexBridge GUI and service launcher")
    parser.add_argument(
        "--run-service",
        metavar="CONFIG_PATH",
        help="Run bot service mode with an explicit config file",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.run_service:
        run_service(args.run_service)
        return

    from codexbridge.gui.app import run_gui

    run_gui()


if __name__ == "__main__":
    main()
