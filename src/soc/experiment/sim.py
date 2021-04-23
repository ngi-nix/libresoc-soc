from openpower.decoder.power_enums import MicrOp

from random import randint, seed
from copy import deepcopy
from math import log


class MemSim:
    def __init__(self, regwid, addrw):
        self.regwid = regwid
        self.ddepth = 1  # regwid//8
        depth = (1 << addrw) // self.ddepth
        self.mem = list(range(0, depth))

    def ld(self, addr):
        return self.mem[addr >> self.ddepth]

    def st(self, addr, data):
        self.mem[addr >> self.ddepth] = data & ((1 << self.regwid)-1)


IADD = 0
ISUB = 1
IMUL = 2
ISHF = 3
IBGT = 4
IBLT = 5
IBEQ = 6
IBNE = 7


class RegSim:
    def __init__(self, rwidth, nregs):
        self.rwidth = rwidth
        self.regs = [0] * nregs

    def op(self, op, op_imm, imm, src1, src2, dest):
        print("regsim op src1, src2", op, op_imm, imm, src1, src2, dest)
        maxbits = (1 << self.rwidth) - 1
        src1 = self.regs[src1] & maxbits
        if op_imm:
            src2 = imm
        else:
            src2 = self.regs[src2] & maxbits
        if op == MicrOp.OP_ADD:
            val = src1 + src2
        elif op == MicrOp.OP_MUL_L64:
            val = src1 * src2
            print("mul src1, src2", src1, src2, val)
        elif op == ISUB:
            val = src1 - src2
        elif op == ISHF:
            val = src1 >> (src2 & maxbits)
        elif op == IBGT:
            val = int(src1 > src2)
        elif op == IBLT:
            val = int(src1 < src2)
        elif op == IBEQ:
            val = int(src1 == src2)
        elif op == IBNE:
            val = int(src1 != src2)
        else:
            return 0  # LD/ST TODO
        val &= maxbits
        self.setval(dest, val)
        return val

    def setval(self, dest, val):
        print("sim setval", dest, hex(val))
        self.regs[dest] = val

    def dump(self, dut):
        for i, val in enumerate(self.regs):
            reg = yield dut.intregs.regs[i].reg
            okstr = "OK" if reg == val else "!ok"
            print("reg %d expected %x received %x %s" % (i, val, reg, okstr))

    def check(self, dut):
        for i, val in enumerate(self.regs):
            reg = yield dut.intregs.regs[i].reg
            if reg != val:
                print("reg %d expected %x received %x\n" % (i, val, reg))
                yield from self.dump(dut)
                assert False
