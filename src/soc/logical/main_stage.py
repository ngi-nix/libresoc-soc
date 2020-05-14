# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.logical.pipe_data import ALUInputData
from soc.alu.pipe_data import ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp

def array_of(count, bitwidth):
    res = []
    for i in range(count):
        res.append(Signal(bitwidth, reset_less=True))
    return res


class LogicalMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")

    def ispec(self):
        return ALUInputData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        a, b, o = self.i.a, self.i.b, self.o.o

        ##########################
        # main switch for logic ops AND, OR and XOR, cmpb, parity, and popcount

        with m.Switch(self.i.ctx.op.insn_type):

            ###### AND, OR, XOR #######
            with m.Case(InternalOp.OP_AND):
                comb += o.eq(a & b)
            with m.Case(InternalOp.OP_OR):
                comb += o.eq(a | b)
            with m.Case(InternalOp.OP_XOR):
                comb += o.eq(a ^ b)

            ###### cmpb #######
            with m.Case(InternalOp.OP_CMPB):
                for i in range(8):
                    slc = slice(i*8, (i+1)*8)
                    with m.If(a[slc] == b[slc]):
                        comb += o[slc].eq(Repl(1, 8))
                    with m.Else():
                        comb += o[slc].eq(Repl(0, 8))

            ###### popcount #######
            with m.Case(InternalOp.OP_POPCNT):
                pc2 = array_of(32, 2)
                pc4 = array_of(16, 3)
                pc8 = array_of(8, 4)
                pc16 = array_of(4, 5)
                pc32 = array_of(2, 6)
                popcnt = Signal(64, reset_less=True)
                for i in range(32):
                    stt, end = i*2, i*2+1
                    comb += pc2[i].eq(Cat(a[stt], Const(0, 1)) +
                                      Cat(a[end], Const(0, 1)))
                for i in range(16):
                    stt, end = i*2, i*2+1
                    comb += pc4[i].eq(Cat(pc2[stt], Const(0, 1)) +
                                      Cat(pc2[end], Const(0, 1)))
                for i in range(8):
                    stt, end = i*2, i*2+1
                    comb += pc8[i].eq(Cat(pc4[stt], Const(0, 1)) +
                                      Cat(pc4[end], Const(0, 1)))
                for i in range(4):
                    stt, end = i*2, i*2+1
                    comb += pc16[i].eq(Cat(pc8[stt], Const(0, 1)) +
                                       Cat(pc8[end], Const(0, 1)))
                for i in range(2):
                    stt, end = i*2, i*2+1
                    comb += pc32[i].eq(Cat(pc16[stt], Const(0, 1)) +
                                       Cat(pc16[end], Const(0, 1)))
                with m.If(self.i.ctx.op.data_len[2:4] == 0b00):
                    # popcntb
                    for i in range(8):
                        comb += popcnt[i*8:i*8+4].eq(pc8[i])
                with m.Elif(self.i.ctx.op.data_len[3] == 0):
                    # popcntw
                    for i in range(2):
                        comb += popcnt[i*32:i*32+5].eq(pc32[i])
                with m.Else():
                    comb += popcnt.eq(Cat(pc32[0], Const(0, 1)) +
                                      Cat(pc32[1], Const(0, 1)))
                comb += o.eq(popcnt)

            ###### parity #######
            # TODO with m.Case(InternalOp.OP_PRTY):
            ###### cntlz #######
            # TODO with m.Case(InternalOp.OP_CNTZ):
            ###### bpermd #######
            # TODO with m.Case(InternalOp.OP_BPERM): - not in microwatt

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
