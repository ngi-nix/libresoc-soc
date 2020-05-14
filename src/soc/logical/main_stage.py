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
        op, a, b, o = self.i.ctx.op, self.i.a, self.i.b, self.o.o

        ##########################
        # main switch for logic ops AND, OR and XOR, cmpb, parity, and popcount

        with m.Switch(op.insn_type):

            ###### AND, OR, XOR #######
            with m.Case(InternalOp.OP_AND):
                comb += o.eq(a & b)
            with m.Case(InternalOp.OP_OR):
                comb += o.eq(a | b)
            with m.Case(InternalOp.OP_XOR):
                comb += o.eq(a ^ b)

            ###### cmpb #######
            with m.Case(InternalOp.OP_CMPB):
                l = []
                for i in range(8):
                    slc = slice(i*8, (i+1)*8)
                    l.append(Repl(a[slc] == b[slc], 8))
                comb += o.eq(Cat(*l))

            ###### popcount #######
            with m.Case(InternalOp.OP_POPCNT):
                # starting from a, perform successive addition-reductions
                # creating arrays big enough to store the sum, each time
                pc = [a]
                # QTY32 2-bit (to take 2x 1-bit sums) etc.
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
                with m.If(op.data_len[2:4] == 0b00):
                    # popcntb - pack 8x 4-bit answers into output
                    for i in range(8):
                        comb += o[i*8:i*8+4].eq(pc8[i])
                with m.Elif(op.data_len[3] == 0):
                    # popcntw - pack 2x 5-bit answers into output
                    for i in range(2):
                        comb += o[i*32:i*32+5].eq(pc32[i])
                with m.Else():
                    # popcntd - put 1x 6-bit answer into output
                    comb += o.eq(popcnt[0])

            ###### parity #######
            with m.Case(InternalOp.OP_PRTY):
                # strange instruction which XORs together the LSBs of each byte
                par0 = Signal(reset_less=True)
                par1 = Signal(reset_less=True)
                comb += par0.eq(Cat(a[0] , a[8] , a[16], a[24]).xor())
                comb += par1.eq(Cat(a[32], a[40], a[48], a[32]).xor())
                with m.If(op.data_len[3] == 1):
                    comb += o.eq(par0 ^ par1)
                with m.Else():
                    comb += o[0].eq(par0)
                    comb += o[32].eq(par1)

            ###### cntlz #######
            # TODO with m.Case(InternalOp.OP_CNTZ):
            ###### bpermd #######
            # TODO with m.Case(InternalOp.OP_BPERM): - not in microwatt

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
