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
from copy import deepcopy

from openpower.decoder.power_decoder import create_pdecode
from openpower.decoder.pseudo.lexer import IndentLexer
from openpower.decoder.orderedset import OrderedSet

# I use the Python AST
#from compiler import ast
import ast

# Helper function


def Assign(autoassign, assignname, left, right, iea_mode):
    names = []
    print("Assign", assignname, left, right)
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
    elif isinstance(left, ast.Subscript):
        ls = left.slice
        # XXX changing meaning of "undefined" to a function
        #if (isinstance(ls, ast.Slice) and isinstance(right, ast.Name) and
        #        right.id == 'undefined'):
        #    # undefined needs to be copied the exact same slice
        #    right = ast.Subscript(right, ls, ast.Load())
        #    return ast.Assign([left], right)
        res = ast.Assign([left], right)
        if autoassign and isinstance(ls, ast.Slice):
            # hack to create a variable pre-declared based on a slice.
            # dividend[0:32] = (RA)[0:32] will create
            #       dividend = [0] * 32
            #       dividend[0:32] = (RA)[0:32]
            # the declaration makes the slice-assignment "work"
            lower, upper, step = ls.lower, ls.upper, ls.step
            print("lower, upper, step", repr(lower), repr(upper), step)
            if not isinstance(lower, ast.Constant) or \
               not isinstance(upper, ast.Constant):
                return res
            qty = ast.Num(upper.value-lower.value)
            keywords = [ast.keyword(arg='repeat', value=qty)]
            l = [ast.Num(0)]
            right = ast.Call(ast.Name("concat", ast.Load()), l, keywords)
            declare = ast.Assign([ast.Name(assignname, ast.Store())], right)
            return [declare, res]
        return res
        # XXX HMMM probably not needed...
        ls = left.slice
        if isinstance(ls, ast.Slice):
            lower, upper, step = ls.lower, ls.upper, ls.step
            print("slice assign", lower, upper, step)
            if step is None:
                ls = (lower, upper, None)
            else:
                ls = (lower, upper, step)
            ls = ast.Tuple(ls)
        return ast.Call(ast.Name("selectassign", ast.Load()),
                        [left.value, ls, right], [])
    else:
        print("Assign fail")
        raise SyntaxError("Can't do that yet")


# I implemented INDENT / DEDENT generation as a post-processing filter

# The original lex token stream contains WS and NEWLINE characters.
# WS will only occur before any other tokens on a line.

# I have three filters.  One tags tokens by adding two attributes.
# "must_indent" is True if the token must be indented from the
# previous code.  The other is "at_line_start" which is True for WS
# and the first non-WS/non-NEWLINE on a line.  It flags the check so
# see if the new line has changed indication level.


# No using Python's approach because Ply supports precedence

# comparison: expr (comp_op expr)*
# arith_expr: term (('+'|'-') term)*
# term: factor (('*'|'/'|'%'|'//') factor)*
# factor: ('+'|'-'|'~') factor | power
# comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'

def make_le_compare(arg):
    (left, right) = arg
    return ast.Call(ast.Name("le", ast.Load()), (left, right), [])


def make_ge_compare(arg):
    (left, right) = arg
    return ast.Call(ast.Name("ge", ast.Load()), (left, right), [])


def make_lt_compare(arg):
    (left, right) = arg
    return ast.Call(ast.Name("lt", ast.Load()), (left, right), [])


def make_gt_compare(arg):
    (left, right) = arg
    return ast.Call(ast.Name("gt", ast.Load()), (left, right), [])


def make_eq_compare(arg):
    (left, right) = arg
    return ast.Call(ast.Name("eq", ast.Load()), (left, right), [])


def make_ne_compare(arg):
    (left, right) = arg
    return ast.Call(ast.Name("ne", ast.Load()), (left, right), [])


binary_ops = {
    "^": ast.BitXor(),
    "&": ast.BitAnd(),
    "|": ast.BitOr(),
    "+": ast.Add(),
    "-": ast.Sub(),
    "*": ast.Mult(),
    "/": ast.FloorDiv(),
    "%": ast.Mod(),
    "<=": make_le_compare,
    ">=": make_ge_compare,
    "<": make_lt_compare,
    ">": make_gt_compare,
    "=": make_eq_compare,
    "!=": make_ne_compare,
}
unary_ops = {
    "+": ast.UAdd(),
    "-": ast.USub(),
    "¬": ast.Invert(),
}


def check_concat(node):  # checks if the comparison is already a concat
    print("check concat", node)
    if not isinstance(node, ast.Call):
        return [node]
    print("func", node.func.id)
    if node.func.id != 'concat':
        return [node]
    if node.keywords:  # a repeated list-constant, don't optimise
        return [node]
    return node.args


# identify SelectableInt pattern [something] * N
# must return concat(something, repeat=N)
def identify_sint_mul_pattern(p):
    if p[2] != '*':  # multiply
        return False
    if not isinstance(p[3], ast.Constant):  # rhs = Num
        return False
    if not isinstance(p[1], ast.List):  # lhs is a list
        return False
    l = p[1].elts
    if len(l) != 1:  # lhs is a list of length 1
        return False
    return True  # yippee!


def apply_trailer(atom, trailer):
    if trailer[0] == "TLIST":
        # assume depth of one
        atom = apply_trailer(atom, trailer[1])
        trailer = trailer[2]
    if trailer[0] == "CALL":
        #p[0] = ast.Expr(ast.Call(p[1], p[2][1], []))
        return ast.Call(atom, trailer[1], [])
        # if p[1].id == 'print':
        #    p[0] = ast.Printnl(ast.Tuple(p[2][1]), None, None)
        # else:
        #    p[0] = ast.CallFunc(p[1], p[2][1], None, None)
    else:
        print("subscript atom", trailer[1])
        #raise AssertionError("not implemented %s" % p[2][0])
        subs = trailer[1]
        if len(subs) == 1:
            idx = subs[0]
        else:
            idx = ast.Slice(subs[0], subs[1], None)
        # if isinstance(atom, ast.Name) and atom.id == 'CR':
            # atom.id = 'CR' # bad hack
            #print ("apply_trailer Subscript", atom.id, idx)
        return ast.Subscript(atom, idx, ast.Load())

##########   Parser (tokens -> AST) ######

# also part of Ply
#import yacc

# https://www.mathcs.emory.edu/~valerie/courses/fall10/155/resources/op_precedence.html
# python operator precedence
# Highest precedence at top, lowest at bottom.
# Operators in the same box evaluate left to right.
#
# Operator Description
# ()                                                     Parentheses (grouping)
# f(args...)                                             Function call
# x[index:index]                                         Slicing
# x[index]                                               Subscription
# x.attribute                                            Attribute reference
# **                                                     Exponentiation
# ~x                                                     Bitwise not
# +x, -x                                                 Positive, negative
# *, /, %                                                mul, div, remainder
# +, -                                                   Addition, subtraction
# <<, >>                                                 Bitwise shifts
# &                                                      Bitwise AND
# ^                                                      Bitwise XOR
# |                                                      Bitwise OR
# in, not in, is, is not, <, <=,  >,  >=, <>, !=, ==     comp, membership, ident
# not x                                                  Boolean NOT
# and                                                    Boolean AND
# or                                                     Boolean OR
# lambda                                                 Lambda expression


class PowerParser:

    precedence = (
        ("left", "EQ", "NE", "GT", "LT", "LE", "GE", "LTU", "GTU"),
        ("left", "BITOR"),
        ("left", "BITXOR"),
        ("left", "BITAND"),
        ("left", "PLUS", "MINUS"),
        ("left", "MULT", "DIV", "MOD"),
        ("left", "INVERT"),
    )

    def __init__(self, form, include_carry_in_write=False):
        self.include_ca_in_write = include_carry_in_write
        self.gprs = {}
        form = self.sd.sigforms[form]
        print(form)
        formkeys = form._asdict().keys()
        self.declared_vars = set()
        for rname in ['RA', 'RB', 'RC', 'RT', 'RS']:
            self.gprs[rname] = None
            self.declared_vars.add(rname)
        self.available_op_fields = set()
        for k in formkeys:
            if k not in self.gprs:
                if k == 'SPR':  # sigh, lower-case to not conflict
                    k = k.lower()
                self.available_op_fields.add(k)
        self.op_fields = OrderedSet()
        self.read_regs = OrderedSet()
        self.uninit_regs = OrderedSet()
        self.write_regs = OrderedSet()
        self.special_regs = OrderedSet()  # see p_atom_name

    # The grammar comments come from Python's Grammar/Grammar file

    # NB: compound_stmt in single_input is followed by extra NEWLINE!
    # file_input: (NEWLINE | stmt)* ENDMARKER

    def p_file_input_end(self, p):
        """file_input_end : file_input ENDMARKER"""
        print("end", p[1])
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
                p[0] = []  # p == 2 --> only a blank line
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
            args = []
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
        elif isinstance(p[1], list):
            p[0] = p[1]
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
        elif isinstance(p[1], ast.Name) and p[1].id == 'TRAP':
            # TRAP needs to actually be a function
            name = ast.Name("self", ast.Load())
            name = ast.Attribute(name, "TRAP", ast.Load())
            p[0] = ast.Call(name, [], [])
        else:
            p[0] = p[1]

    # expr_stmt: testlist (augassign (yield_expr|testlist) |
    #                      ('=' (yield_expr|testlist))*)
    # augassign: ('+=' | '-=' | '*=' | '/=' | '%=' | '&=' | '|=' | '^=' |
    #             '<<=' | '>>=' | '**=' | '//=')
    def p_expr_stmt(self, p):
        """expr_stmt : testlist ASSIGNEA testlist
                     | testlist ASSIGN testlist
                     | testlist """
        print("expr_stmt", p)
        if len(p) == 2:
            # a list of expressions
            #p[0] = ast.Discard(p[1])
            p[0] = p[1]
        else:
            iea_mode = p[2] == '<-iea'
            name = None
            autoassign = False
            if isinstance(p[1], ast.Name):
                name = p[1].id
            elif isinstance(p[1], ast.Subscript):
                if isinstance(p[1].value, ast.Name):
                    name = p[1].value.id
                    if name in self.gprs:
                        # add to list of uninitialised
                        self.uninit_regs.add(name)
                    autoassign = (name not in self.declared_vars and
                                  name not in self.special_regs)
            elif isinstance(p[1], ast.Call) and p[1].func.id in ['GPR', 'SPR']:
                print(astor.dump_tree(p[1]))
                # replace GPR(x) with GPR[x]
                idx = p[1].args[0]
                p[1] = ast.Subscript(p[1].func, idx, ast.Load())
            elif isinstance(p[1], ast.Call) and p[1].func.id == 'MEM':
                print("mem assign")
                print(astor.dump_tree(p[1]))
                p[1].func.id = "memassign"  # change function name to set
                p[1].args.append(p[3])
                p[0] = p[1]
                print("mem rewrite")
                print(astor.dump_tree(p[0]))
                return
            else:
                print("help, help")
                print(astor.dump_tree(p[1]))
            print("expr assign", name, p[1])
            if name and name in self.gprs:
                self.write_regs.add(name)  # add to list of regs to write
            p[0] = Assign(autoassign, name, p[1], p[3], iea_mode)
            if name:
                self.declared_vars.add(name)

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
                         | switch_stmt
                         | for_stmt
                         | funcdef
        """
        p[0] = p[1]

    def p_break_stmt(self, p):
        """break_stmt : BREAK
        """
        p[0] = ast.Break()

    def p_for_stmt(self, p):
        """for_stmt : FOR atom EQ test TO test COLON suite
                    | DO atom EQ test TO test COLON suite
        """
        start = p[4]
        end = p[6]
        if start.value > end.value:  # start greater than end, must go -ve
            # auto-subtract-one (sigh) due to python range
            end = ast.BinOp(p[6], ast.Add(), ast.Constant(-1))
            arange = [start, end, ast.Constant(-1)]
        else:
            # auto-add-one (sigh) due to python range
            end = ast.BinOp(p[6], ast.Add(), ast.Constant(1))
            arange = [start, end]
        it = ast.Call(ast.Name("range", ast.Load()), arange, [])
        p[0] = ast.For(p[2], it, p[8], [])

    def p_while_stmt(self, p):
        """while_stmt : DO WHILE test COLON suite ELSE COLON suite
                      | DO WHILE test COLON suite
        """
        if len(p) == 6:
            p[0] = ast.While(p[3], p[5], [])
        else:
            p[0] = ast.While(p[3], p[5], p[8])

    def p_switch_smt(self, p):
        """switch_stmt : SWITCH LPAR atom RPAR COLON NEWLINE INDENT switches DEDENT
        """
        switchon = p[3]
        print("switch stmt")
        print(astor.dump_tree(p[1]))

        cases = []
        current_cases = []  # for deferral
        for (case, suite) in p[8]:
            print("for", case, suite)
            if suite is None:
                for c in case:
                    current_cases.append(ast.Num(c))
                continue
            if case == 'default':  # last
                break
            for c in case:
                current_cases.append(ast.Num(c))
            print("cases", current_cases)
            compare = ast.Compare(switchon, [ast.In()],
                                  [ast.List(current_cases, ast.Load())])
            current_cases = []
            cases.append((compare, suite))

        print("ended", case, current_cases)
        if case == 'default':
            if current_cases:
                compare = ast.Compare(switchon, [ast.In()],
                                      [ast.List(current_cases, ast.Load())])
                cases.append((compare, suite))
            cases.append((None, suite))

        cases.reverse()
        res = []
        for compare, suite in cases:
            print("after rev", compare, suite)
            if compare is None:
                assert len(res) == 0, "last case should be default"
                res = suite
            else:
                if not isinstance(res, list):
                    res = [res]
                res = ast.If(compare, suite, res)
        p[0] = res

    def p_switches(self, p):
        """switches : switch_list switch_default
                    | switch_default
        """
        if len(p) == 3:
            p[0] = p[1] + [p[2]]
        else:
            p[0] = [p[1]]

    def p_switch_list(self, p):
        """switch_list : switch_case switch_list
                       | switch_case
        """
        if len(p) == 3:
            p[0] = [p[1]] + p[2]
        else:
            p[0] = [p[1]]

    def p_switch_case(self, p):
        """switch_case : CASE LPAR atomlist RPAR COLON suite
        """
        # XXX bad hack
        if isinstance(p[6][0], ast.Name) and p[6][0].id == 'fallthrough':
            p[6] = None
        p[0] = (p[3], p[6])

    def p_switch_default(self, p):
        """switch_default : DEFAULT COLON suite
        """
        p[0] = ('default', p[3])

    def p_atomlist(self, p):
        """atomlist : atom COMMA atomlist
                    | atom
        """
        assert isinstance(p[1], ast.Constant), "case must be numbers"
        if len(p) == 4:
            p[0] = [p[1].value] + p[3]
        else:
            p[0] = [p[1].value]

    def p_if_stmt(self, p):
        """if_stmt : IF test COLON suite ELSE COLON if_stmt
                   | IF test COLON suite ELSE COLON suite
                   | IF test COLON suite
        """
        if len(p) == 8 and isinstance(p[7], ast.If):
            p[0] = ast.If(p[2], p[4], [p[7]])
        elif len(p) == 5:
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
                      | comparison MOD comparison
                      | comparison EQ comparison
                      | comparison NE comparison
                      | comparison LE comparison
                      | comparison GE comparison
                      | comparison LTU comparison
                      | comparison GTU comparison
                      | comparison LT comparison
                      | comparison GT comparison
                      | comparison BITOR comparison
                      | comparison BITXOR comparison
                      | comparison BITAND comparison
                      | PLUS comparison
                      | comparison MINUS
                      | INVERT comparison
                      | comparison APPEND comparison
                      | power"""
        if len(p) == 4:
            print(list(p))
            if p[2] == '<u':
                p[0] = ast.Call(ast.Name("ltu", ast.Load()), (p[1], p[3]), [])
            elif p[2] == '>u':
                p[0] = ast.Call(ast.Name("gtu", ast.Load()), (p[1], p[3]), [])
            elif p[2] == '||':
                l = check_concat(p[1]) + check_concat(p[3])
                p[0] = ast.Call(ast.Name("concat", ast.Load()), l, [])
            elif p[2] in ['/', '%']:
                # bad hack: if % or / used anywhere other than div/mod ops,
                # do % or /.  however if the argument names are "dividend"
                # we must call the special trunc_divs and trunc_rems functions
                l, r = p[1], p[3]
                # actual call will be "dividend / divisor" - just check
                # LHS name
                # XXX DISABLE BAD HACK (False)
                if False and isinstance(l, ast.Name) and l.id == 'dividend':
                    if p[2] == '/':
                        fn = 'trunc_divs'
                    else:
                        fn = 'trunc_rems'
                    # return "function trunc_xxx(l, r)"
                    p[0] = ast.Call(ast.Name(fn, ast.Load()), (l, r), [])
                else:
                    # return "l {binop} r"
                    p[0] = ast.BinOp(p[1], binary_ops[p[2]], p[3])
            elif p[2] in ['<', '>', '=', '<=', '>=', '!=']:
                p[0] = binary_ops[p[2]]((p[1], p[3]))
            elif identify_sint_mul_pattern(p):
                keywords = [ast.keyword(arg='repeat', value=p[3])]
                l = p[1].elts
                p[0] = ast.Call(ast.Name("concat", ast.Load()), l, keywords)
            else:
                p[0] = ast.BinOp(p[1], binary_ops[p[2]], p[3])
        elif len(p) == 3:
            if isinstance(p[2], str) and p[2] == '-':
                p[0] = ast.UnaryOp(unary_ops[p[2]], p[1])
            else:
                p[0] = ast.UnaryOp(unary_ops[p[1]], p[2])
        else:
            p[0] = p[1]

    # power: atom trailer* ['**' factor]
    # trailers enables function calls (and subscripts).
    # so this is 'trailerlist'
    def p_power(self, p):
        """power : atom
                 | atom trailerlist"""
        if len(p) == 2:
            print("power dump atom notrailer")
            print(astor.dump_tree(p[1]))
            p[0] = p[1]
        else:
            print("power dump atom")
            print(astor.dump_tree(p[1]))
            print("power dump trailerlist")
            print(astor.dump_tree(p[2]))
            p[0] = apply_trailer(p[1], p[2])
            if isinstance(p[1], ast.Name):
                name = p[1].id
                if name in ['RA', 'RS', 'RB', 'RC', 'RT']:
                    self.read_regs.add(name)

    def p_atom_name(self, p):
        """atom : NAME"""
        name = p[1]
        if name in self.available_op_fields:
            self.op_fields.add(name)
        if name == 'overflow':
            self.write_regs.add(name)
        if self.include_ca_in_write:
            if name in ['CA', 'CA32']:
                self.write_regs.add(name)
        if name in ['CR', 'LR', 'CTR', 'TAR', 'FPSCR', 'MSR', 'SVSTATE']:
            self.special_regs.add(name)
            self.write_regs.add(name)  # and add to list to write
        p[0] = ast.Name(id=name, ctx=ast.Load())

    def p_atom_number(self, p):
        """atom : BINARY
                | NUMBER
                | HEX
                | STRING"""
        p[0] = ast.Constant(p[1])

    # '[' [listmaker] ']' |

    def p_atom_listmaker(self, p):
        """atom : LBRACK listmaker RBRACK"""
        p[0] = p[2]

    def p_listmaker(self, p):
        """listmaker : test COMMA listmaker
                     | test
        """
        if len(p) == 2:
            p[0] = ast.List([p[1]], ast.Load())
        else:
            p[0] = ast.List([p[1]] + p[3].nodes, ast.Load())

    def p_atom_tuple(self, p):
        """atom : LPAR testlist RPAR"""
        print("tuple", p[2])
        print("astor dump")
        print(astor.dump_tree(p[2]))

        if isinstance(p[2], ast.Name):
            name = p[2].id
            print("tuple name", name)
            if name in self.gprs:
                self.read_regs.add(name)  # add to list of regs to read
                #p[0] = ast.Subscript(ast.Name("GPR", ast.Load()), ast.Str(p[2].id))
                # return
            p[0] = p[2]
        elif isinstance(p[2], ast.BinOp):
            if isinstance(p[2].left, ast.Name) and \
               isinstance(p[2].right, ast.Constant) and \
                    p[2].right.value == 0 and \
                    p[2].left.id in self.gprs:
                rid = p[2].left.id
                self.read_regs.add(rid)  # add to list of regs to read
                # create special call to GPR.getz
                gprz = ast.Name("GPR", ast.Load())
                # get testzero function
                gprz = ast.Attribute(gprz, "getz", ast.Load())
                # *sigh* see class GPR.  we need index itself not reg value
                ridx = ast.Name("_%s" % rid, ast.Load())
                p[0] = ast.Call(gprz, [ridx], [])
                print("tree", astor.dump_tree(p[0]))
            else:
                p[0] = p[2]
        else:
            p[0] = p[2]

    def p_trailerlist(self, p):
        """trailerlist : trailer trailerlist
                       | trailer
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = ("TLIST", p[1], p[2])

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

    # subscript: '.' '.' '.' | test | [test] ':' [test]

    def p_subscript(self, p):
        """subscript : test COLON test
                     | test
        """
        if len(p) == 4:
            # add one to end
            if isinstance(p[3], ast.Constant):
                end = ast.Constant(p[3].value+1)
            else:
                end = ast.BinOp(p[3], ast.Add(), ast.Constant(1))
            p[0] = [p[1], end]
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
        # print "Error!", repr(p)
        raise SyntaxError(p)


class GardenSnakeParser(PowerParser):
    def __init__(self, lexer=None, debug=False, form=None, incl_carry=False):
        self.sd = create_pdecode()
        PowerParser.__init__(self, form, incl_carry)
        self.debug = debug
        if lexer is None:
            lexer = IndentLexer(debug=0)
        self.lexer = lexer
        self.tokens = lexer.tokens
        self.parser = yacc.yacc(module=self, start="file_input_end",
                                debug=debug, write_tables=False)

    def parse(self, code):
        # self.lexer.input(code)
        result = self.parser.parse(code, lexer=self.lexer, debug=self.debug)
        return ast.Module(result)


###### Code generation ######

#from compiler import misc, syntax, pycodegen

_CACHED_PARSERS = {}
_CACHE_PARSERS = True


class GardenSnakeCompiler(object):
    def __init__(self, debug=False, form=None, incl_carry=False):
        if _CACHE_PARSERS:
            try:
                parser = _CACHED_PARSERS[debug, form, incl_carry]
            except KeyError:
                parser = GardenSnakeParser(debug=debug, form=form,
                                           incl_carry=incl_carry)
                _CACHED_PARSERS[debug, form, incl_carry] = parser

            self.parser = deepcopy(parser)
        else:
            self.parser = GardenSnakeParser(debug=debug, form=form,
                                            incl_carry=incl_carry)

    def compile(self, code, mode="exec", filename="<string>"):
        tree = self.parser.parse(code)
        print("snake")
        pprint(tree)
        return tree
        #misc.set_filename(filename, tree)
        return compile(tree, mode="exec", filename="<string>")
        # syntax.check(tree)
        gen = pycodegen.ModuleCodeGenerator(tree)
        code = gen.getCode()
        return code
