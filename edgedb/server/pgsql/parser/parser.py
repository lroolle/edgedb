##
# Copyright (c) 2010 Sprymix Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import os

import Parsing
import pyggy

from semantix.utils import debug

from . import parsermeta
from .error import PgSQLParserError

class _ParserSpecs:
    parser_spec = None
    lexer_spec = None

    @classmethod
    def get_specs(cls):
        if cls.parser_spec is None:
            from . import parserdef
            cls.parser_spec = Parsing.Spec(
                                parserdef,
                                pickleFile=cls.localpath("parserdef.pickle"),
                                skinny=True,
                                logFile=cls.localpath("parserdef.log"),
                                #graphFile=cls.localpath("parserdef.dot"),
                                verbose='caos.pgsql.parser' in debug.channels)

        if cls.lexer_spec is None:
            _, lexer_spec = pyggy.getlexer(cls.localpath("pgsql.pyl"))
            cls.lexer_spec = lexer_spec.lexspec

        return cls.parser_spec, cls.lexer_spec

    @classmethod
    def localpath(cls, filename):
        return os.path.join(os.path.dirname(__file__), filename)

    @classmethod
    def cleanup(cls):
        cls.parser_spec = None
        cls.lexer_spec = None


class PgSQLParser:
    def __init__(self):
        self.parser_spec = None
        self.lexer_spec = None
        self.lexer = None
        self.parser = None

    def cleanup(self):
        self.parser_spec = None
        self.lexer_spec = None
        self.lexer = None
        self.parser = None
        _ParserSpecs.cleanup()

    def reset_parser(self, input):
        if self.parser_spec is None:
            self.parser_spec, self.lexer_spec = _ParserSpecs.get_specs()
            self.lexer = pyggy.lexer.lexer(self.lexer_spec)
            self.parser = Parsing.Lr(self.parser_spec)

        self.parser.reset()
        self.lexer.setinputstr(input)

    @debug.debug
    def parse(self, input):
        self.reset_parser(input)

        try:
            tok = self.lexer.token()

            while tok:
                token = parsermeta.TokenMeta.for_lex_token(tok)(self.parser, self.lexer.value)

                """LOG [caos.pgsql.lexer] TOKEN
                print('%r' % token)
                """

                self.parser.token(token)
                tok = self.lexer.token()

            self.parser.eoi()

        except Parsing.SyntaxError as e:
            raise PgSQLParserError(e.args[0]) from e

        return self.parser.start[0].val
