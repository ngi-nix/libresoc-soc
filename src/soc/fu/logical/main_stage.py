# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from nmutil.clz import CLZ
from soc.fu.logical.pipe_data import LogicalInputData
from soc.fu.logical.bpermd import Bpermd
from soc.fu.logical.popcount import Popcount
from soc.fu.logical.pipe_data import LogicalOutputData
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange


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
        m.submodules.popcount = popcount = Popcount()

        ##########################
        # main switch for logic ops AND, OR and XOR, cmpb, parity, and popcount

        with m.Switch(op.insn_type):

            ###################
            ###### AND, OR, XOR  v3.0B p92-95

            with m.Case(MicrOp.OP_AND):
                comb += o.data.eq(a & b)
            with m.Case(MicrOp.OP_OR):
                comb += o.data.eq(a | b)
            with m.Case(MicrOp.OP_XOR):
                comb += o.data.eq(a ^ b)

            ###################
            ###### cmpb  v3.0B p97

            with m.Case(MicrOp.OP_CMPB):
                l = []
                for i in range(8):
                    slc = slice(i*8, (i+1)*8)
                    l.append(Repl(a[slc] == b[slc], 8))
                comb += o.data.eq(Cat(*l))

            ###################
            ###### popcount v3.0B p97, p98

            with m.Case(MicrOp.OP_POPCNT):
                comb += popcount.a.eq(a)
                comb += popcount.b.eq(b)
                comb += popcount.data_len.eq(op.data_len)
                comb += o.data.eq(popcount.o)

            ###################
            ###### parity v3.0B p98

            with m.Case(MicrOp.OP_PRTY):
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

            ###################
            ###### cntlz v3.0B p99

            with m.Case(MicrOp.OP_CNTZ):
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

            ###################
            ###### bpermd v3.0B p100

            with m.Case(MicrOp.OP_BPERM):
                comb += bpermd.rs.eq(a)
                comb += bpermd.rb.eq(b)
                comb += o.data.eq(bpermd.ra)

            with m.Default():
                comb += o.ok.eq(0)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.data.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
