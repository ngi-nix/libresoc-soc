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
                # starting from a, perform successive addition-reductions
                pc = [a]
                work = [(32, 2), (16, 3), (8, 4), (4, 5), (2, 6), (1, 6)]
                for l, b in work:
                    pc.append(array_of(l, b))
                pc8 = pc[3]     # array of 8 8-bit counts (popcntb)
                pc32 = pc[5]    # array of 2 32-bit counts (popcntw)
                popcnt = pc[-1] # array of 1 64-bit count (popcntd)
                # cascade-tree of adds
                for idx, (l, b) in enumerate(work):
                    for i in range(l):
                        stt, end = i*2, i*2+1
                        src, dst = pc[idx], pc[idx+1]
                        comb += dst[i].eq(Cat(src[stt], Const(0, 1)) +
                                          Cat(src[end], Const(0, 1)))
                # decode operation length
                with m.If(self.i.ctx.op.data_len[2:4] == 0b00):
                    # popcntb - pack 8x 4-bit answers into output
                    for i in range(8):
                        comb += o[i*8:i*8+4].eq(pc8[i])
                with m.Elif(self.i.ctx.op.data_len[3] == 0):
                    # popcntw - pack 2x 5-bit answers into output
                    for i in range(2):
                        comb += o[i*32:i*32+5].eq(pc32[i])
                with m.Else():
                    # popcntd - put 1x 6-bit answer into output
                    comb += o.eq(popcnt[0])

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
