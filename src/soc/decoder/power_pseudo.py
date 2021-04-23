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
import ast

from openpower.decoder.power_decoder import create_pdecode
from nmigen.back.pysim import Simulator, Delay
from nmigen import Module, Signal

from openpower.decoder.pseudo.parser import GardenSnakeCompiler
from openpower.decoder.selectable_int import SelectableInt, selectconcat
from openpower.decoder.isa.caller import GPR, Mem


####### Test code #######

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
    print (n)
    if (RS)[63-n] = 0b1 then
        leave
    n  <- n + 1
RA <- EXTZ64(n)
print (RA)
"""

cmpi = """
if      a < EXTS(SI) then
    c <- 0b100
else if a > EXTS(SI) then
    c <- 0b010
"""

cmpi = """
RA[0:1] <- 0b11
"""

cmpi = """
in_range <-  ((x | y) &
              (a | b))
in_range <-  (x + y) - (a + b)
"""

cmpi = """
(RA)[0:1] <- 1
src1    <- EXTZ((RA)[56:63])
CR[4*BF+32] <- 0b0
in_range <- src21lo  <= src1 & src1 <=  src21hi 
"""

cmpeqb = """
src1 <- GPR[RA]
src1 <- src1[0:56]
"""

addpcis = """
D <- d0||d1||d2
"""

testmul = """
x <- [0] * 16
RT <- (RA) + EXTS(SI || [0]*16)
"""

testgetzero = """
RS <- (RA|0)
RS <- RS + 1
print(RS)
"""

testcat = """
RT <- (load_data[56:63] || load_data[48:55]
    || load_data[40:47] || load_data[32:39]
    || load_data[24:31] || load_data[16:23]
    || load_data[8:15]  || load_data[0:7])
"""

testgpr = """
GPR(5) <- x
"""
testmem = """
a <- (RA|0)
b <- (RB|0)
RA <- MEM(RB, 2)
EA <- a + 1
MEM(EA, 1) <- (RS)[56:63]
RB <- RA
RA <- EA
"""

testgprslice = """
MEM(EA, 4) <- GPR(r)[32:63]
#x <- x[0][32:63]
"""

testdo = r"""
do i = 0 to 7
    print(i)
"""

testcond = """
ctr_ok <- BO[2] | ((CTR[M:63] != 0) ^ BO[3])
cond_ok <- BO[0] | ¬(CR[BI+32] ^  BO[1])
"""

lswx = """
if RA = 0 then EA <- 0
else           EA <- (RA)
if NB = 0 then n <-  32
else           n <-  NB
r <- RT - 1
i <- 32
do while n > 0
    if i = 32 then
        r <- (r + 1) % 32
        GPR(r) <- 0
    GPR(r)[i:i+7] <- MEM(EA, 1)
    i <- i + 8
    if i = 64 then i <- 32
    EA <- EA + 1
    n <- n - 1
"""

_lswx = """
GPR(r)[x] <- 1
"""

switchtest = """
switch (n)
    case(1): x <- 5
    case(2): fallthrough
    case(3):
        x <- 3
    case(4): fallthrough
    default:
        x <- 9
"""

hextest = """
RT <- 0x0001_a000_0000_0000
"""

code = hextest
#code = lswx
#code = testcond
#code = testdo
#code = _bpermd
#code = testmul
#code = testgetzero
#code = testcat
#code = testgpr
#code = testmem
#code = testgprslice
#code = testreg
#code = cnttzd
#code = cmpi
#code = cmpeqb
#code = addpcis
#code = bpermd


def tolist(num):
    l = []
    for i in range(64):
        l.append(1 if (num & (1 << i)) else 0)
    l.reverse()
    return l


def get_reg_hex(reg):
    return hex(reg.value)


def convert_to_python(pcode, form, incl_carry):

    print("form", form)
    gsc = GardenSnakeCompiler(form=form, incl_carry=incl_carry)

    tree = gsc.compile(pcode, mode="exec", filename="string")
    tree = ast.fix_missing_locations(tree)
    regsused = {'read_regs': gsc.parser.read_regs,
                'write_regs': gsc.parser.write_regs,
                'uninit_regs': gsc.parser.uninit_regs,
                'special_regs': gsc.parser.special_regs,
                'op_fields': gsc.parser.op_fields}
    return astor.to_source(tree), regsused


def test():

    gsc = GardenSnakeCompiler(debug=True)

    gsc.regfile = {}
    for i in range(32):
        gsc.regfile[i] = i
    gsc.gpr = GPR(gsc.parser.sd, gsc.regfile)
    gsc.mem = Mem()

    _compile = gsc.compile

    tree = _compile(code, mode="single", filename="string")
    tree = ast.fix_missing_locations(tree)
    print(ast.dump(tree))

    print("astor dump")
    print(astor.dump_tree(tree))
    print("to source")
    source = astor.to_source(tree)
    print(source)

    # sys.exit(0)

    # Set up the GardenSnake run-time environment
    def print_(*args):
        print("args", args)
        print("-->", " ".join(map(str, args)))

    from openpower.decoder.helpers import (EXTS64, EXTZ64, ROTL64, ROTL32, MASK,
                                     trunc_div, trunc_rem)

    d = {}
    d["print"] = print_
    d["EXTS64"] = EXTS64
    d["EXTZ64"] = EXTZ64
    d["trunc_div"] = trunc_div
    d["trunc_rem"] = trunc_rem
    d["SelectableInt"] = SelectableInt
    d["concat"] = selectconcat
    d["GPR"] = gsc.gpr
    d["MEM"] = gsc.mem
    d["memassign"] = gsc.mem.memassign

    form = 'X'
    gsc.gpr.set_form(form)
    getform = gsc.parser.sd.sigforms[form]._asdict()
    #print ("getform", form)
    # for k, f in getform.items():
    #print (k, f)
    #d[k] = getform[k]

    compiled_code = compile(source, mode="exec", filename="<string>")

    m = Module()
    comb = m.d.comb
    instruction = Signal(32)

    m.submodules.decode = decode = gsc.parser.sd
    comb += decode.raw_opcode_in.eq(instruction)
    sim = Simulator(m)

    instr = [0x11111117]

    def process():
        for ins in instr:
            print("0x{:X}".format(ins & 0xffffffff))

            # ask the decoder to decode this binary data (endian'd)
            yield decode.bigendian.eq(0)  # little / big?
            yield instruction.eq(ins)          # raw binary instr.
            yield Delay(1e-6)

            # uninitialised regs, drop them into dict for function
            for rname in gsc.parser.uninit_regs:
                d[rname] = SelectableInt(0, 64)  # uninitialised (to zero)
                print("uninitialised", rname, hex(d[rname].value))

            # read regs, drop them into dict for function
            for rname in gsc.parser.read_regs:
                regidx = yield getattr(decode.sigforms['X'], rname)
                d[rname] = gsc.gpr[regidx]  # contents of regfile
                d["_%s" % rname] = regidx  # actual register value
                print("read reg", rname, regidx, hex(d[rname].value))

            exec(compiled_code, d)  # code gets executed here in dict "d"
            print("Done")

            print(d.keys())  # shows the variables that may have been created

            print(decode.sigforms['X'])
            x = yield decode.sigforms['X'].RS
            ra = yield decode.sigforms['X'].RA
            rb = yield decode.sigforms['X'].RB
            print("RA", ra, d['RA'])
            print("RB", rb, d['RB'])
            print("RS", x)

            for wname in gsc.parser.write_regs:
                reg = getform[wname]
                regidx = yield reg
                print("write regs", regidx, wname, d[wname], reg)
                gsc.gpr[regidx] = d[wname]

    sim.add_process(process)
    with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                       traces=decode.ports()):
        sim.run()

    gsc.gpr.dump()

    for i in range(0, len(gsc.mem.mem), 16):
        hexstr = []
        for j in range(16):
            hexstr.append("%02x" % gsc.mem.mem[i+j])
        hexstr = ' '.join(hexstr)
        print("mem %4x" % i, hexstr)


if __name__ == '__main__':
    test()
