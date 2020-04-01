# Based on GardenSnake - a parser generator demonstration program
# GardenSnake was released into the Public Domain by Andrew Dalke.

# Portions of this work are derived from Python's Grammar definition
# and may be covered under the Python copyright and license
#
#          Andrew Dalke / Dalke Scientific Software, LLC
#             30 August 2006 / Cape Town, South Africa

# Modifications for inclusion in PLY distribution
from pprint import pprint
from ply import lex, yacc
import astor

from soc.decoder.power_decoder import create_pdecode
from soc.decoder.pseudo.lexer import IndentLexer

# I use the Python AST
#from compiler import ast
import ast

# Helper function
def Assign(left, right):
    names = []
    if isinstance(left, ast.Name):
        # Single assignment on left
        # XXX when doing IntClass, which will have an "eq" function,
        # this is how to access it
        #   eq = ast.Attribute(left, "eq")   # get eq fn
        #   return ast.Call(eq, [right], []) # now call left.eq(right)
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

def check_concat(node): # checks if the comparison is already a concat
    print (node)
    if not isinstance(node, ast.Call):
        return [node]
    if node[0].id != 'concat':
        return node
    return node[1]


##########   Parser (tokens -> AST) ######

# also part of Ply
#import yacc

class PowerParser:

    precedence = (
        ("left", "EQ", "GT", "LT"),
        ("left", "PLUS", "MINUS"),
        ("left", "MULT", "DIV"),
        )

    def __init__(self):
        self.gprs = {}
        for rname in ['RA', 'RB', 'RC', 'RT', 'RS']:
            self.gprs[rname] = None
        self.read_regs = []
        self.write_regs = []

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
        p[0] = ast.FunctionDef(p[2], p[3], p[5], ())

    # parameters: '(' [varargslist] ')'
    def p_parameters(self, p):
        """parameters : LPAR RPAR
                      | LPAR varargslist RPAR"""
        if len(p) == 3:
            args=[]
        else:
            args = p[2]
        p[0] = ast.arguments(args=args, vararg=None, kwarg=None, defaults=[])


    # varargslist: (fpdef ['=' test] ',')* ('*' NAME [',' '**' NAME] |
    # '**' NAME) |
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
        if isinstance(p[1], ast.Call):
            p[0] = ast.Expr(p[1])
        else:
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
            if p[1].id in self.gprs:
                self.write_regs.append(p[1].id) # add to list of regs to write
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
        print ("tuple", p[2])
        if isinstance(p[2], ast.Name):
            print ("tuple name", p[2].id)
            if p[2].id in self.gprs:
                self.read_regs.append(p[2].id) # add to list of regs to read
                #p[0] = ast.Subscript(ast.Name("GPR"), ast.Str(p[2].id))
                #return
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



    # arglist: (argument ',')* (argument [',']| '*' test [',' '**' test]
    # | '**' test)
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
        PowerParser.__init__(self)
        if lexer is None:
            lexer = IndentLexer(debug=1)
        self.lexer = lexer
        self.tokens = lexer.tokens
        self.parser = yacc.yacc(module=self, start="file_input_end",
                                debug=False, write_tables=False)

        self.sd = create_pdecode()

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

