# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from nmutil.clz import CLZ
from soc.fu.logical.pipe_data import LogicalInputData
from soc.fu.logical.bpermd import Bpermd
from soc.fu.logical.pipe_data import LogicalOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange


def array_of(count, bitwidth):
    res = []
    for i in range(count):
        res.append(Signal(bitwidth, reset_less=True,
                          name=f"pop_{bitwidth}_{i}"))
    return res


class LogicalMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return LogicalInputData(self.pspec)

    def ospec(self):
        return LogicalOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op, a, b, o = self.i.ctx.op, self.i.a, self.i.b, self.o.o

        comb += o.ok.eq(1) # overridden if no op activates


        m.submodules.bpermd = bpermd = Bpermd(64)

        ##########################
        # main switch for logic ops AND, OR and XOR, cmpb, parity, and popcount

        with m.Switch(op.insn_type):

            ###### AND, OR, XOR #######
            with m.Case(InternalOp.OP_AND):
                comb += o.data.eq(a & b)
            with m.Case(InternalOp.OP_OR):
                comb += o.data.eq(a | b)
            with m.Case(InternalOp.OP_XOR):
                comb += o.data.eq(a ^ b)

            ###### cmpb #######
            with m.Case(InternalOp.OP_CMPB):
                l = []
                for i in range(8):
                    slc = slice(i*8, (i+1)*8)
                    l.append(Repl(a[slc] == b[slc], 8))
                comb += o.data.eq(Cat(*l))

            ###### popcount #######
            with m.Case(InternalOp.OP_POPCNT):
                # starting from a, perform successive addition-reductions
                # creating arrays big enough to store the sum, each time
                pc = [a]
                # QTY32 2-bit (to take 2x 1-bit sums) etc.
                work = [(32, 2), (16, 3), (8, 4), (4, 5), (2, 6), (1, 7)]
                for l, b in work:
                    pc.append(array_of(l, b))
                pc8 = pc[3]     # array of 8 8-bit counts (popcntb)
                pc32 = pc[5]    # array of 2 32-bit counts (popcntw)
                popcnt = pc[-1]  # array of 1 64-bit count (popcntd)
                # cascade-tree of adds
                for idx, (l, b) in enumerate(work):
                    for i in range(l):
                        stt, end = i*2, i*2+1
                        src, dst = pc[idx], pc[idx+1]
                        comb += dst[i].eq(Cat(src[stt], Const(0, 1)) +
                                          Cat(src[end], Const(0, 1)))
                # decode operation length
                with m.If(op.data_len == 1):
                    # popcntb - pack 8x 4-bit answers into output
                    for i in range(8):
                        comb += o[i*8:(i+1)*8].eq(pc8[i])
                with m.Elif(op.data_len == 4):
                    # popcntw - pack 2x 5-bit answers into output
                    for i in range(2):
                        comb += o[i*32:(i+1)*32].eq(pc32[i])
                with m.Else():
                    # popcntd - put 1x 6-bit answer into output
                    comb += o.data.eq(popcnt[0])

            ###### parity #######
            with m.Case(InternalOp.OP_PRTY):
                # strange instruction which XORs together the LSBs of each byte
                par0 = Signal(reset_less=True)
                par1 = Signal(reset_less=True)
                comb += par0.eq(Cat(a[0], a[8], a[16], a[24]).xor())
                comb += par1.eq(Cat(a[32], a[40], a[48], a[56]).xor())
                with m.If(op.data_len[3] == 1):
                    comb += o.data.eq(par0 ^ par1)
                with m.Else():
                    comb += o[0].eq(par0)
                    comb += o[32].eq(par1)

            ###### cntlz #######
            with m.Case(InternalOp.OP_CNTZ):
                XO = self.fields.FormX.XO[0:-1]
                count_right = Signal(reset_less=True)
                comb += count_right.eq(XO[-1])

                cntz_i = Signal(64, reset_less=True)
                a32 = Signal(32, reset_less=True)
                comb += a32.eq(a[0:32])

                with m.If(op.is_32bit):
                    comb += cntz_i.eq(Mux(count_right, a32[::-1], a32))
                with m.Else():
                    comb += cntz_i.eq(Mux(count_right, a[::-1], a))

                m.submodules.clz = clz = CLZ(64)
                comb += clz.sig_in.eq(cntz_i)
                comb += o.data.eq(Mux(op.is_32bit, clz.lz-32, clz.lz))

            ###### bpermd #######
            with m.Case(InternalOp.OP_BPERM):
                comb += bpermd.rs.eq(a)
                comb += bpermd.rb.eq(self.i.b)
                comb += o.data.eq(bpermd.ra)

            with m.Default():
                comb += o.ok.eq(0)

        ###### context, pass-through #####

        comb += self.o.ctx.eq(self.i.ctx)

        return m
