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

from soc.decoder.power_decoder import create_pdecode
from nmigen.back.pysim import Simulator, Delay
from nmigen import Module, Signal

from soc.decoder.pseudo.parser import GardenSnakeCompiler
from soc.decoder.selectable_int import SelectableInt, selectconcat

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

#code = testreg
#code = cnttzd
#code = cmpi
#code = cmpeqb
code = addpcis
#code = bpermd

def tolist(num):
    l = []
    for i in range(64):
        l.append(1 if (num & (1<<i)) else 0)
    l.reverse()
    return l


def get_reg_hex(reg):
    return hex(reg.value)


class GPR(dict):
    def __init__(self, sd, regfile):
        dict.__init__(self)
        self.sd = sd
        self.regfile = regfile
        for i in range(32):
            self[i] = SelectableInt(0, 64)

    def set_form(self, form):
        self.form = form

    def ___getitem__(self, attr):
        print ("GPR getitem", attr)
        getform = self.sd.sigforms[self.form]
        rnum = getattr(getform, attr)
        print ("GPR get", rnum, rnum, dir(rnum))
        l = list(rnum)
        print (l[0]._as_const())
        #for x in rnum:
            #print (x, x.value, dir(x))
            #print (x.value, dir(x.value))
        print (list(rnum))
        return self.regfile[rnum]


def convert_to_python(pcode):

    gsc = GardenSnakeCompiler()

    tree = gsc.compile(pcode, mode="exec", filename="string")
    tree = ast.fix_missing_locations(tree)
    return astor.to_source(tree)


def test():

    gsc = GardenSnakeCompiler()

    # XXX unused!  see GPR instead
    gsc.regfile = {}
    for i in range(32):
        gsc.regfile[i] = 0
    gsc.gpr = GPR(gsc.parser.sd, gsc.regfile)

    _compile = gsc.compile

    tree = _compile(code, mode="single", filename="string")
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

    from soc.decoder.helpers import (EXTS64, EXTZ64, ROTL64, ROTL32, MASK,)

    d = {}
    d["print"] = print_
    d["EXTS64"] = EXTS64
    d["EXTZ64"] = EXTZ64
    d["SelectableInt"] = SelectableInt
    d["concat"] = selectconcat
    d["GPR"] = gsc.gpr

    form = 'X'
    gsc.gpr.set_form(form)
    getform = gsc.parser.sd.sigforms[form]._asdict()
    #print ("getform", form)
    #for k, f in getform.items():
        #print (k, f)
        #d[k] = getform[k]

    compiled_code = compile(source, mode="exec", filename="<string>")

    m = Module()
    comb = m.d.comb
    instruction = Signal(32)

    m.submodules.decode = decode =  gsc.parser.sd
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

            # read regs, drop them into dict for function
            for rname in gsc.parser.uninit_regs:
                d[rname] = SelectableInt(0, 64) # uninitialised (to zero)
                print ("uninitialised", rname, get_reg_hex(d[rname]))

            for rname in gsc.parser.read_regs:
                regidx = yield getattr(decode.sigforms['X'], rname)
                d[rname] = gsc.gpr[regidx]
                print ("read reg", rname, regidx, get_reg_hex(d[rname]))

            exec (compiled_code, d)
            print ("Done")

            print (d.keys())

            print (decode.sigforms['X'])
            x = yield decode.sigforms['X'].RS
            ra = yield decode.sigforms['X'].RA
            print ("RA", ra, d['RA'])
            print ("RS", x)

            for wname in gsc.parser.write_regs:
                reg = getform[wname]
                print ("write regs", wname, d[wname], reg)
                regidx = yield reg
                gsc.gpr[regidx] = d[wname]

    sim.add_process(process)
    with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                       traces=decode.ports()):
        sim.run()

    for i in range(len(gsc.gpr)):
        print ("regfile", i, get_reg_hex(gsc.gpr[i]))


if __name__ == '__main__':
    test()
