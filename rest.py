#!/usr/bin/env python3

import logging
import sys
from argparse import ArgumentParser
from debugboard import Board, TACException
from flask import Flask
from flask_restful import Resource, Api, reqparse
from werkzeug.exceptions import BadRequest
from werkzeug.serving import run_simple

app = Flask(__name__)
api = Api(app)

logger = logging.getLogger()
boards = {}

rparser = reqparse.RequestParser()
rparser.add_argument("value", type=int, help="1 for setting pin HIGH, 0 for setting pin LOW")


class BoardView(Resource):
    def get(self, boardid):
        return boards.get(boardid, {})


class BoardList(Resource):
    def get(self):
        return boards


class QuickMethodView(Resource):
    def get(self, boardid, name):
        b = boards.get(boardid, {})
        if b:
            return b.quick_methods.get(name, {})
        return {}

    def put(self, boardid, name):
        b = boards.get(boardid, {})
        if b:
            try:
                getattr(b, name)()
            except:
                raise TACException
        return b.pins


class QuickMethodList(Resource):
    def get(self, boardid):
        b = boards.get(boardid, {})
        if b:
            return b.quick_methods
        return {}


class CommandView(Resource):
    def get(self, boardid, name):
        b = boards.get(boardid, {})
        if b:
            return b.commands.get(name, {})
        return {}

    def put(self, boardid, name):
        args = rparser.parse_args()
        value = args.get("value")
        if value is None:
            raise BadRequest("insufficient parameters")
        b = boards.get(boardid, {})
        if b:
            try:
                c = getattr(b, name)
                if c:
                    c(value)
            except:
                raise TACException
        return b.pins


class CommandList(Resource):
    def get(self, boardid):
        b = boards.get(boardid, {})
        if b:
            return b.commands
        return {}


class PinView(Resource):

    def get(self, boardid, pinid):
        b = boards.get(boardid, {})
        if b:
            return b.pins.get(pinid, {})
        return {}

    def put(self, boardid, pinid):
        args = rparser.parse_args()
        value = args.get("value")
        if value is None:
            raise BadRequest("insufficient parameters")
        b = boards.get(boardid, {})
        if b:
            p = b.pins.get(pinid)
            p.set(value)
        return b.pins.get(pinid)


class PinList(Resource):
    def get(self, boardid):
        b = boards.get(boardid, {})
        if b:
            return b.pins
        return {}


class PortView(Resource):
    def get(self, boardid, portid):
        b = boards.get(boardid, {})
        if b:
            return b.ports.get(portid, {})
        return {}


class PortList(Resource):
    def get(self, boardid):
        b = boards.get(boardid, {})
        if b:
            return b.ports
        return {}


api.add_resource(BoardList, "/")
api.add_resource(BoardView, "/<boardid>")
api.add_resource(PinView, "/<boardid>/pin/<pinid>")
api.add_resource(PinList, "/<boardid>/pin")
api.add_resource(QuickMethodView, "/<boardid>/quick/<name>")
api.add_resource(QuickMethodList, "/<boardid>/quick")
api.add_resource(PortView, "/<boardid>/port/<portid>")
api.add_resource(PortList, "/<boardid>/port")
api.add_resource(CommandView, "/<boardid>/command/<name>")
api.add_resource(CommandList, "/<boardid>/command")


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("--serial", nargs='+', help="Debug board serial number", required=True)
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

    for serial in args.serial:
        boards.update({serial: Board.create_board(serial, args.tac_config_path)})

    run_simple("0.0.0.0", 5000, app)
