# Based on GardenSnake - a parser generator demonstration program
# GardenSnake was released into the Public Domain by Andrew Dalke.

# Portions of this work are derived from Python's Grammar definition
# and may be covered under the Python copyright and license
#
#          Andrew Dalke / Dalke Scientific Software, LLC
#             30 August 2006 / Cape Town, South Africa

# Modifications for inclusion in PLY distribution
import sys
from pprint import pprint
from copy import copy
from ply import lex, yacc
import astor

from soc.decoder.power_fieldsn import create_sigdecode


# I use the Python AST
#from compiler import ast
import ast

# Helper function
def Assign(left, right):
    names = []
    if isinstance(left, ast.Name):
        # Single assignment on left
        return ast.Assign([ast.Name(left.id, ast.Store())], right)
    elif isinstance(left, ast.Tuple):
        # List of things - make sure they are Name nodes
        names = []
        for child in left.getChildren():
            if not isinstance(child, ast.Name):
                raise SyntaxError("that assignment not supported")
            names.append(child.name)
        ass_list = [ast.AssName(name, 'OP_ASSIGN') for name in names]
        return ast.Assign([ast.AssTuple(ass_list)], right)
    else:
        raise SyntaxError("Can't do that yet")


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
                raise IndentationError("indentation increase but not in new block")
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

## No using Python's approach because Ply supports precedence

# comparison: expr (comp_op expr)*
# arith_expr: term (('+'|'-') term)*
# term: factor (('*'|'/'|'%'|'//') factor)*
# factor: ('+'|'-'|'~') factor | power
# comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'

def make_lt_compare(arg):
    (left, right) = arg
    return ast.Compare(left, [ast.Lt()], [right])
def make_gt_compare(arg):
    (left, right) = arg
    return ast.Compare(left, [ast.Gt()], [right])
def make_eq_compare(arg):
    (left, right) = arg
    return ast.Compare(left, [ast.Eq()], [right])


binary_ops = {
    "+": ast.Add(),
    "-": ast.Sub(),
    "*": ast.Mult(),
    "/": ast.Div(),
    "<": make_lt_compare,
    ">": make_gt_compare,
    "=": make_eq_compare,
}
unary_ops = {
    "+": ast.Add,
    "-": ast.Sub,
    }
precedence = (
    ("left", "EQ", "GT", "LT"),
    ("left", "PLUS", "MINUS"),
    ("left", "MULT", "DIV"),
    )

def check_concat(node): # checks if the comparison is already a concat
    print (node)
    if not isinstance(node, ast.Call):
        return [node]
    if node[0].id != 'concat':
        return node
    return node[1]
##### Lexer ######
#import lex
import decimal

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
        t.value = int(t.value, 2)
        return t

    #t_NUMBER = r'\d+'
    # taken from decmial.py but without the leading sign
    def t_NUMBER(self, t):
        r"""(\d+(\.\d*)?|\.\d+)([eE][-+]? \d+)?"""
        t.value = int(t.value)
        return t

    def t_STRING(self, t):
        r"'([^\\']+|\\'|\\\\)*'"  # I think this is right ...
        t.value=t.value[1:-1].decode("string-escape") # .swapcase() # for fun
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


##########   Parser (tokens -> AST) ######

# also part of Ply
#import yacc

class PowerParser:

    # The grammar comments come from Python's Grammar/Grammar file

    ## NB: compound_stmt in single_input is followed by extra NEWLINE!
    # file_input: (NEWLINE | stmt)* ENDMARKER

    def p_file_input_end(self, p):
        """file_input_end : file_input ENDMARKER"""
        print ("end", p[1])
        p[0] = p[1]

    def p_file_input(self, p):
        """file_input : file_input NEWLINE
                      | file_input stmt
                      | NEWLINE
                      | stmt"""
        if isinstance(p[len(p)-1], str):
            if len(p) == 3:
                p[0] = p[1]
            else:
                p[0] = [] # p == 2 --> only a blank line
        else:
            if len(p) == 3:
                p[0] = p[1] + p[2]
            else:
                p[0] = p[1]


    # funcdef: [decorators] 'def' NAME parameters ':' suite
    # ignoring decorators
    def p_funcdef(self, p):
        "funcdef : DEF NAME parameters COLON suite"
        p[0] = ast.Function(None, p[2], list(p[3]), (), 0, None, p[5])

    # parameters: '(' [varargslist] ')'
    def p_parameters(self, p):
        """parameters : LPAR RPAR
                      | LPAR varargslist RPAR"""
        if len(p) == 3:
            p[0] = []
        else:
            p[0] = p[2]


    # varargslist: (fpdef ['=' test] ',')* ('*' NAME [',' '**' NAME] | '**' NAME) |
    # highly simplified
    def p_varargslist(self, p):
        """varargslist : varargslist COMMA NAME
                       | NAME"""
        if len(p) == 4:
            p[0] = p[1] + p[3]
        else:
            p[0] = [p[1]]

    # stmt: simple_stmt | compound_stmt
    def p_stmt_simple(self, p):
        """stmt : simple_stmt"""
        # simple_stmt is a list
        p[0] = p[1]

    def p_stmt_compound(self, p):
        """stmt : compound_stmt"""
        p[0] = [p[1]]

    # simple_stmt: small_stmt (';' small_stmt)* [';'] NEWLINE
    def p_simple_stmt(self, p):
        """simple_stmt : small_stmts NEWLINE
                       | small_stmts SEMICOLON NEWLINE"""
        p[0] = p[1]

    def p_small_stmts(self, p):
        """small_stmts : small_stmts SEMICOLON small_stmt
                       | small_stmt"""
        if len(p) == 4:
            p[0] = p[1] + [p[3]]
        else:
            p[0] = [p[1]]

    # small_stmt: expr_stmt | print_stmt  | del_stmt | pass_stmt | flow_stmt |
    #    import_stmt | global_stmt | exec_stmt | assert_stmt
    def p_small_stmt(self, p):
        """small_stmt : flow_stmt
                      | break_stmt
                      | expr_stmt"""
        p[0] = p[1]

    # expr_stmt: testlist (augassign (yield_expr|testlist) |
    #                      ('=' (yield_expr|testlist))*)
    # augassign: ('+=' | '-=' | '*=' | '/=' | '%=' | '&=' | '|=' | '^=' |
    #             '<<=' | '>>=' | '**=' | '//=')
    def p_expr_stmt(self, p):
        """expr_stmt : testlist ASSIGN testlist
                     | testlist """
        if len(p) == 2:
            # a list of expressions
            #p[0] = ast.Discard(p[1])
            p[0] = p[1]
        else:
            p[0] = Assign(p[1], p[3])

    def p_flow_stmt(self, p):
        "flow_stmt : return_stmt"
        p[0] = p[1]

    # return_stmt: 'return' [testlist]
    def p_return_stmt(self, p):
        "return_stmt : RETURN testlist"
        p[0] = ast.Return(p[2])


    def p_compound_stmt(self, p):
        """compound_stmt : if_stmt
                         | while_stmt
                         | for_stmt
                         | funcdef
        """
        p[0] = p[1]

    def p_break_stmt(self, p):
        """break_stmt : BREAK
        """
        p[0] = ast.Break()

    def p_for_stmt(self, p):
        """for_stmt : FOR test EQ test TO test COLON suite
        """
        p[0] = ast.While(p[2], p[4], [])
        # auto-add-one (sigh) due to python range
        start = p[4]
        end = ast.BinOp(p[6], ast.Add(), ast.Constant(1))
        it = ast.Call(ast.Name("range"), [start, end], [])
        p[0] = ast.For(p[2], it, p[8], [])

    def p_while_stmt(self, p):
        """while_stmt : DO WHILE test COLON suite ELSE COLON suite
                      | DO WHILE test COLON suite
        """
        if len(p) == 6:
            p[0] = ast.While(p[3], p[5], [])
        else:
            p[0] = ast.While(p[3], p[5], p[8])

    def p_if_stmt(self, p):
        """if_stmt : IF test COLON suite ELSE COLON suite
                   | IF test COLON suite
        """
        if len(p) == 5:
            p[0] = ast.If(p[2], p[4], [])
        else:
            p[0] = ast.If(p[2], p[4], p[7])

    def p_suite(self, p):
        """suite : simple_stmt
                 | NEWLINE INDENT stmts DEDENT"""
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = p[3]


    def p_stmts(self, p):
        """stmts : stmts stmt
                 | stmt"""
        if len(p) == 3:
            p[0] = p[1] + p[2]
        else:
            p[0] = p[1]

    def p_comparison(self, p):
        """comparison : comparison PLUS comparison
                      | comparison MINUS comparison
                      | comparison MULT comparison
                      | comparison DIV comparison
                      | comparison LT comparison
                      | comparison EQ comparison
                      | comparison GT comparison
                      | PLUS comparison
                      | MINUS comparison
                      | comparison APPEND comparison
                      | power"""
        if len(p) == 4:
            print (list(p))
            if p[2] == '||':
                l = check_concat(p[1]) + check_concat(p[3])
                p[0] = ast.Call(ast.Name("concat"), l, [])
            elif p[2] in ['<', '>', '=']:
                p[0] = binary_ops[p[2]]((p[1],p[3]))
            else:
                p[0] = ast.BinOp(p[1], binary_ops[p[2]], p[3])
        elif len(p) == 3:
            p[0] = unary_ops[p[1]](p[2])
        else:
            p[0] = p[1]

    # power: atom trailer* ['**' factor]
    # trailers enables function calls (and subscripts).
    # I only allow one level of calls
    # so this is 'trailer'
    def p_power(self, p):
        """power : atom
                 | atom trailer"""
        if len(p) == 2:
            p[0] = p[1]
        else:
            if p[2][0] == "CALL":
                #p[0] = ast.Expr(ast.Call(p[1], p[2][1], []))
                p[0] = ast.Call(p[1], p[2][1], [])
                #if p[1].id == 'print':
                #    p[0] = ast.Printnl(ast.Tuple(p[2][1]), None, None)
                #else:
                #    p[0] = ast.CallFunc(p[1], p[2][1], None, None)
            else:
                print (p[2][1])
                #raise AssertionError("not implemented %s" % p[2][0])
                subs = p[2][1]
                if len(subs) == 1:
                    idx = subs[0]
                else:
                    idx = ast.Slice(subs[0], subs[1], None)
                p[0] = ast.Subscript(p[1], idx)

    def p_atom_name(self, p):
        """atom : NAME"""
        p[0] = ast.Name(p[1], ctx=ast.Load())

    def p_atom_number(self, p):
        """atom : BINARY
                | NUMBER
                | STRING"""
        p[0] = ast.Constant(p[1])

    #'[' [listmaker] ']' |

    def p_atom_listmaker(self, p):
        """atom : LBRACK listmaker RBRACK"""
        p[0] = p[2]

    def p_listmaker(self, p):
        """listmaker : test COMMA listmaker
                     | test
        """
        if len(p) == 2:
            p[0] = ast.List([p[1]])
        else:
            p[0] = ast.List([p[1]] + p[3].nodes)

    def p_atom_tuple(self, p):
        """atom : LPAR testlist RPAR"""
        p[0] = p[2]

    # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
    def p_trailer(self, p):
        """trailer : trailer_arglist
                   | trailer_subscript
        """
        p[0] = p[1]

    def p_trailer_arglist(self, p):
        "trailer_arglist : LPAR arglist RPAR"
        p[0] = ("CALL", p[2])

    def p_trailer_subscript(self, p):
        "trailer_subscript : LBRACK subscript RBRACK"
        p[0] = ("SUBS", p[2])

    #subscript: '.' '.' '.' | test | [test] ':' [test]

    def p_subscript(self, p):
        """subscript : test COLON test
                     | test
        """
        if len(p) == 4:
            p[0] = [p[1], p[3]]
        else:
            p[0] = [p[1]]


    # testlist: test (',' test)* [',']
    # Contains shift/reduce error
    def p_testlist(self, p):
        """testlist : testlist_multi COMMA
                    | testlist_multi """
        if len(p) == 2:
            p[0] = p[1]
        else:
            # May need to promote singleton to tuple
            if isinstance(p[1], list):
                p[0] = p[1]
            else:
                p[0] = [p[1]]
        # Convert into a tuple?
        if isinstance(p[0], list):
            p[0] = ast.Tuple(p[0])

    def p_testlist_multi(self, p):
        """testlist_multi : testlist_multi COMMA test
                          | test"""
        if len(p) == 2:
            # singleton
            p[0] = p[1]
        else:
            if isinstance(p[1], list):
                p[0] = p[1] + [p[3]]
            else:
                # singleton -> tuple
                p[0] = [p[1], p[3]]


    # test: or_test ['if' or_test 'else' test] | lambdef
    #  as I don't support 'and', 'or', and 'not' this works down to 'comparison'
    def p_test(self, p):
        "test : comparison"
        p[0] = p[1]



    # arglist: (argument ',')* (argument [',']| '*' test [',' '**' test] | '**' test)
    # XXX INCOMPLETE: this doesn't allow the trailing comma
    def p_arglist(self, p):
        """arglist : arglist COMMA argument
                   | argument"""
        if len(p) == 4:
            p[0] = p[1] + [p[3]]
        else:
            p[0] = [p[1]]

    # argument: test [gen_for] | test '=' test  # Really [keyword '='] test
    def p_argument(self, p):
        "argument : test"
        p[0] = p[1]

    def p_error(self, p):
        #print "Error!", repr(p)
        raise SyntaxError(p)


class GardenSnakeParser(PowerParser):
    def __init__(self, lexer = None):
        if lexer is None:
            lexer = IndentLexer(debug=1)
        self.lexer = lexer
        self.tokens = lexer.tokens
        self.parser = yacc.yacc(module=self, start="file_input_end",
                                debug=False, write_tables=False)

        self.sd = create_sigdecode()

    def parse(self, code):
        self.lexer.input(code)
        result = self.parser.parse(lexer = self.lexer, debug=False)
        return ast.Module(result)


###### Code generation ######

#from compiler import misc, syntax, pycodegen

class GardenSnakeCompiler(object):
    def __init__(self):
        self.parser = GardenSnakeParser()
    def compile(self, code, mode="exec", filename="<string>"):
        tree = self.parser.parse(code)
        print ("snake")
        pprint(tree)
        return tree
        #misc.set_filename(filename, tree)
        return compile(tree, mode="exec", filename="<string>")
        #syntax.check(tree)
        gen = pycodegen.ModuleCodeGenerator(tree)
        code = gen.getCode()
        return code

####### Test code #######

from soc.decoder.power_fieldsn import create_sigdecode

bpermd = r"""
perm <- [0] * 8
if index < 64:
    index <- (RS)[8*i:8*i+7]
RA <- [0]*56 || perm[0:7]
print (RA)
"""

bpermd = r"""
if index < 64 then index <- 0
else index <- 5
do while index < 5
    index <- 0
    leave
for i = 0 to 7
    index <- 0
"""

_bpermd = r"""
for i = 0 to 7
   index <- (RS)[8*i:8*i+7]
   if index < 64 then
        permi <- (RB)[index]
   else
        permi <- 0
RA <- [0]*56|| perm[0:7]
"""

cnttzd = """
n  <- 0
do while n < 64
   if (RS)[63-n] = 0b1 then
        leave
   n  <- n + 1
RA <- EXTZ64(n)
"""

code = cnttzd
#code = bpermd

lexer = IndentLexer(debug=1)
# Give the lexer some input
print ("code")
print (code)
lexer.input(code)

# Tokenize
while True:
    tok = lexer.token()
    if not tok:
        break      # No more input
    print(tok)

#sys.exit(0)

sd = create_sigdecode()
print ("forms", sd.df.forms)
for f in sd.df.FormX:
    print (f)

gsc = GardenSnakeCompiler()
_compile = gsc.compile

tree = _compile(code, mode="single", filename="string")
import ast
tree = ast.fix_missing_locations(tree)
print ( ast.dump(tree) )

print ("astor dump")
print (astor.dump_tree(tree))
print ("to source")
source = astor.to_source(tree)
print (source)

#sys.exit(0)

# Set up the GardenSnake run-time environment
def print_(*args):
    print ("args", args)
    print ("-->", " ".join(map(str,args)))

def listconcat(l1, l2):
    return l1 + l2

d = {}
d["print"] = print_
d["concat"] = listconcat

form = 'X'
getform = getattr(gsc.parser.sd.df, "Form%s" % form)
print (getform)
for k, f in sd.df.instrs[form].items():
    d[k] = getattr(getform, k)

compiled_code = compile(source, mode="exec", filename="<string>")

exec (compiled_code, d)
print ("Done")

