# Based on GardenSnake - a parser generator demonstration program
# GardenSnake was released into the Public Domain by Andrew Dalke.

# Portions of this work are derived from Python's Grammar definition
# and may be covered under the Python copyright and license
#
#          Andrew Dalke / Dalke Scientific Software, LLC
#             30 August 2006 / Cape Town, South Africa

# Modifications for inclusion in PLY distribution
from copy import copy
from ply import lex
from soc.decoder.selectable_int import SelectableInt

## I implemented INDENT / DEDENT generation as a post-processing filter

# The original lex token stream contains WS and NEWLINE characters.
# WS will only occur before any other tokens on a line.

# I have three filters.  One tags tokens by adding two attributes.
# "must_indent" is True if the token must be indented from the
# previous code.  The other is "at_line_start" which is True for WS
# and the first non-WS/non-NEWLINE on a line.  It flags the check so
# see if the new line has changed indication level.

# Python's syntax has three INDENT states
#  0) no colon hence no need to indent
#  1) "if 1: go()" - simple statements have a COLON but no need for an indent
#  2) "if 1:\n  go()" - complex statements have a COLON NEWLINE and must indent
NO_INDENT = 0
MAY_INDENT = 1
MUST_INDENT = 2

# turn into python-like colon syntax from pseudo-code syntax
def python_colonify(lexer, tokens):

    forwhile_seen = False
    for token in tokens:
        #print ("track colon token", token, token.type)

        if token.type == 'THEN':
            # turn then into colon
            token.type = "COLON"
            yield token
        elif token.type == 'ELSE':
            yield token
            token = copy(token)
            token.type = "COLON"
            yield token
        elif token.type in ['WHILE', 'FOR']:
            forwhile_seen = True
            yield token
        elif token.type == 'NEWLINE':
            if forwhile_seen:
                ctok = copy(token)
                ctok.type = "COLON"
                yield ctok
                forwhile_seen = False
            yield token
        else:
            yield token


# only care about whitespace at the start of a line
def track_tokens_filter(lexer, tokens):
    oldignore = lexer.lexignore
    lexer.at_line_start = at_line_start = True
    indent = NO_INDENT
    saw_colon = False
    for token in tokens:
        #print ("track token", token, token.type)
        token.at_line_start = at_line_start

        if token.type == "COLON":
            at_line_start = False
            indent = MAY_INDENT
            token.must_indent = False

        elif token.type == "NEWLINE":
            at_line_start = True
            if indent == MAY_INDENT:
                indent = MUST_INDENT
            token.must_indent = False

        elif token.type == "WS":
            assert token.at_line_start == True
            at_line_start = True
            token.must_indent = False

        else:
            # A real token; only indent after COLON NEWLINE
            if indent == MUST_INDENT:
                token.must_indent = True
            else:
                token.must_indent = False
            at_line_start = False
            indent = NO_INDENT

        # really bad hack that changes ignore lexer state.
        # when "must indent" is seen (basically "real tokens" seen)
        # then ignore whitespace.
        if token.must_indent:
            lexer.lexignore = ('ignore', ' ')
        else:
            lexer.lexignore = oldignore

        token.indent = indent
        yield token
        lexer.at_line_start = at_line_start

def _new_token(type, lineno):
    tok = lex.LexToken()
    tok.type = type
    tok.value = None
    tok.lineno = lineno
    tok.lexpos = -1
    return tok

# Synthesize a DEDENT tag
def DEDENT(lineno):
    return _new_token("DEDENT", lineno)

# Synthesize an INDENT tag
def INDENT(lineno):
    return _new_token("INDENT", lineno)


# Track the indentation level and emit the right INDENT / DEDENT events.
def indentation_filter(tokens):
    # A stack of indentation levels; will never pop item 0
    levels = [0]
    token = None
    depth = 0
    prev_was_ws = False
    for token in tokens:
        if 1:
            print ("Process", depth, token.indent, token,)
            if token.at_line_start:
                print ("at_line_start",)
            if token.must_indent:
                print ("must_indent",)
            print

        # WS only occurs at the start of the line
        # There may be WS followed by NEWLINE so
        # only track the depth here.  Don't indent/dedent
        # until there's something real.
        if token.type == "WS":
            assert depth == 0
            depth = len(token.value)
            prev_was_ws = True
            # WS tokens are never passed to the parser
            continue

        if token.type == "NEWLINE":
            depth = 0
            if prev_was_ws or token.at_line_start:
                # ignore blank lines
                continue
            # pass the other cases on through
            yield token
            continue

        # then it must be a real token (not WS, not NEWLINE)
        # which can affect the indentation level

        prev_was_ws = False
        if token.must_indent:
            # The current depth must be larger than the previous level
            if not (depth > levels[-1]):
                raise IndentationError("expected an indented block")

            levels.append(depth)
            yield INDENT(token.lineno)

        elif token.at_line_start:
            # Must be on the same level or one of the previous levels
            if depth == levels[-1]:
                # At the same level
                pass
            elif depth > levels[-1]:
                raise IndentationError("indent increase but not in new block")
            else:
                # Back up; but only if it matches a previous level
                try:
                    i = levels.index(depth)
                except ValueError:
                    raise IndentationError("inconsistent indentation")
                for _ in range(i+1, len(levels)):
                    yield DEDENT(token.lineno)
                    levels.pop()

        yield token

    ### Finished processing ###

    # Must dedent any remaining levels
    if len(levels) > 1:
        assert token is not None
        for _ in range(1, len(levels)):
            yield DEDENT(token.lineno)


# The top-level filter adds an ENDMARKER, if requested.
# Python's grammar uses it.
def filter(lexer, add_endmarker = True):
    token = None
    tokens = iter(lexer.token, None)
    tokens = python_colonify(lexer, tokens)
    tokens = track_tokens_filter(lexer, tokens)
    for token in indentation_filter(tokens):
        yield token

    if add_endmarker:
        lineno = 1
        if token is not None:
            lineno = token.lineno
        yield _new_token("ENDMARKER", lineno)

##### Lexer ######

class PowerLexer:
    tokens = (
        'DEF',
        'IF',
        'THEN',
        'ELSE',
        'FOR',
        'TO',
        'DO',
        'WHILE',
        'BREAK',
        'NAME',
        'NUMBER',  # Python decimals
        'BINARY',  # Python binary
        'STRING',  # single quoted strings only; syntax of raw strings
        'LPAR',
        'RPAR',
        'LBRACK',
        'RBRACK',
        'COLON',
        'EQ',
        'ASSIGN',
        'LT',
        'GT',
        'PLUS',
        'MINUS',
        'MULT',
        'DIV',
        'APPEND',
        'RETURN',
        'WS',
        'NEWLINE',
        'COMMA',
        'SEMICOLON',
        'INDENT',
        'DEDENT',
        'ENDMARKER',
        )

    # Build the lexer
    def build(self,**kwargs):
         self.lexer = lex.lex(module=self, **kwargs)

    def t_BINARY(self, t):
        r"""0b[01]+"""
        t.value = SelectableInt(int(t.value, 2), len(t.value)-2)
        return t

    #t_NUMBER = r'\d+'
    # taken from decmial.py but without the leading sign
    def t_NUMBER(self, t):
        r"""(\d+(\.\d*)?|\.\d+)([eE][-+]? \d+)?"""
        t.value = int(t.value)
        return t

    def t_STRING(self, t):
        r"'([^\\']+|\\'|\\\\)*'"  # I think this is right ...
        print (repr(t.value))
        t.value=t.value[1:-1]
        return t

    t_COLON = r':'
    t_EQ = r'='
    t_ASSIGN = r'<-'
    t_LT = r'<'
    t_GT = r'>'
    t_PLUS = r'\+'
    t_MINUS = r'-'
    t_MULT = r'\*'
    t_DIV = r'/'
    t_COMMA = r','
    t_SEMICOLON = r';'
    t_APPEND = r'\|\|'

    # Ply nicely documented how to do this.

    RESERVED = {
      "def": "DEF",
      "if": "IF",
      "then": "THEN",
      "else": "ELSE",
      "leave": "BREAK",
      "for": "FOR",
      "to": "TO",
      "while": "WHILE",
      "do": "DO",
      "return": "RETURN",
      }

    def t_NAME(self, t):
        r'[a-zA-Z_][a-zA-Z0-9_]*'
        t.type = self.RESERVED.get(t.value, "NAME")
        return t

    # Putting this before t_WS let it consume lines with only comments in
    # them so the latter code never sees the WS part.  Not consuming the
    # newline.  Needed for "if 1: #comment"
    def t_comment(self, t):
        r"[ ]*\043[^\n]*"  # \043 is '#'
        pass


    # Whitespace
    def t_WS(self, t):
        r'[ ]+'
        if t.lexer.at_line_start and t.lexer.paren_count == 0 and \
                                     t.lexer.brack_count == 0:
            return t

    # Don't generate newline tokens when inside of parenthesis, eg
    #   a = (1,
    #        2, 3)
    def t_newline(self, t):
        r'\n+'
        t.lexer.lineno += len(t.value)
        t.type = "NEWLINE"
        if t.lexer.paren_count == 0 and t.lexer.brack_count == 0:
            return t

    def t_LBRACK(self, t):
        r'\['
        t.lexer.brack_count += 1
        return t

    def t_RBRACK(self, t):
        r'\]'
        # check for underflow?  should be the job of the parser
        t.lexer.brack_count -= 1
        return t

    def t_LPAR(self, t):
        r'\('
        t.lexer.paren_count += 1
        return t

    def t_RPAR(self, t):
        r'\)'
        # check for underflow?  should be the job of the parser
        t.lexer.paren_count -= 1
        return t

    #t_ignore = " "

    def t_error(self, t):
        raise SyntaxError("Unknown symbol %r" % (t.value[0],))
        print ("Skipping", repr(t.value[0]))
        t.lexer.skip(1)

# Combine Ply and my filters into a new lexer

class IndentLexer(PowerLexer):
    def __init__(self, debug=0, optimize=0, lextab='lextab', reflags=0):
        self.build(debug=debug, optimize=optimize,
                                lextab=lextab, reflags=reflags)
        self.token_stream = None
    def input(self, s, add_endmarker=True):
        self.lexer.paren_count = 0
        self.lexer.brack_count = 0
        self.lexer.input(s)
        self.token_stream = filter(self.lexer, add_endmarker)

    def token(self):
        try:
            return next(self.token_stream)
        except StopIteration:
            return None

if __name__ == '__main__':

    # quick test/demo
    cnttzd = """
    n  <- 0
    do while n < 64
       if (RS)[63-n] = 0b1 then
            leave
       n  <- n + 1
    RA <- EXTZ64(n)
    print (RA)
    """

    code = cnttzd

    lexer = IndentLexer(debug=1)
    # Give the lexer some input
    print ("code")
    print (code)
    lexer.input(code)

