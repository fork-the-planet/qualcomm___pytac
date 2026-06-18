#!/usr/bin/env python3

# Copyright (c) 2025-2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

import logging
import sys
from argparse import ArgumentParser

from . import DEFAULT_TAC_CONFIG_PATH, __version__

logger = logging.getLogger()


def _setup_logging(level):
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def build_parser():
    parser = ArgumentParser(
        prog="pytac",
        description="Test Automation Controller (TAC/Alpaca) for Qualcomm debug boards.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--shell",
        action="store_true",
        help="Run the interactive shell (default)",
    )
    mode.add_argument("--service", action="store_true", help="Run the REST API service")

    parser.add_argument(
        "--serial",
        nargs="+",
        help="Debug board serial number(s). Required for --service "
        "(one or more); for --shell a single serial is used.",
    )
    parser.add_argument(
        "--config-file-path",
        help="Path to a single config file. --shell only; use for debugging "
        "the config file syntax.",
    )
    parser.add_argument(
        "--tac-config-path",
        default=DEFAULT_TAC_CONFIG_PATH,
        help="Path to directory with TAC configs (devicelist.json + .tcnf "
        "files). Required for FTDI/PSOC boards; Bughopper boards need no configs.",
    )
    parser.add_argument(
        "--log-level", default="DEBUG", help="Log level (default: DEBUG)"
    )
    parser.add_argument(
        "--hostname",
        default="0.0.0.0",
        help="--service only: host name the server attaches to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        default=5000,
        type=int,
        help="--service only: port on the host to attach to (default: 5000)",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)

    if args.service:
        if not args.serial:
            parser.error("--service requires --serial")
        from .service import run_service

        run_service(args.serial, args.tac_config_path, args.hostname, args.port)
    else:  # --shell
        if not args.serial and not args.config_file_path:
            parser.error("--shell requires --serial or --config-file-path")
        from .shell import run_shell

        serial = args.serial[0] if args.serial else None
        run_shell(serial, args.config_file_path, args.tac_config_path)


if __name__ == "__main__":
    main()
