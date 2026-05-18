# Copyright (c)i 2025-2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

import logging
import sys
from argparse import ArgumentParser
from debugboard import Board
from cmd import Cmd

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def make_h(name, comment=None):
    def h(cls, *args):
        print("Set GPIO value to HIGH (1) or LOW (0)")
        print("When called without parameters, GPIO is set to LOW")
        if comment:
            print(comment)
    return h


def make_f(quick_method):
    def f(cls, *args):
        quick_method.call()
    return f


class AlpacaCmd(Cmd):

    def do_quit(self, line):
        print("Quitting")
        return True

    do_EOF = do_quit


if __name__ == '__main__':
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--serial", help="Debug board serial number")
    group.add_argument("--config-file-path", help="Path to config file. Only use for debugging the config file syntax")
    parser.add_argument("--tac-config-path",
                        help="Path to directory with TAC configs",
                        default="./tac_configs")
    parser.add_argument("--log-level", help="Log level", default="DEBUG")

    args = parser.parse_args()

    logger.setLevel(args.log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(args.log_level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    board = None
    if args.serial:
        board = Board.create_board(args.serial, args.tac_config_path)
    if args.config_file_path:
        board = Board.create_from_config(args.config_file_path)
    for pin in board.pins.values():
        method_name = f"do_{pin.command}"
        help_name =  f"help_{pin.command}"
        logger.debug(f"Adding {method_name}")
        method = pin.set
        help_f = make_h(pin.command, pin.get("help_hint"))
        setattr(AlpacaCmd, method_name, method)
        setattr(AlpacaCmd, help_name, help_f)

    for name, method in board.quick_methods.items():
        method_name = f"do_{name}"
        logger.debug(f"Adding {method_name}")
        setattr(AlpacaCmd, method_name, make_f(method))

    cmd = AlpacaCmd()
    cmd.cmdloop()

