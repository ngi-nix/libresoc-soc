# This stage is intended to do most of the work of executing the Arithmetic
# instructions. This would be like the additions, compares, and sign-extension
# as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage

# License: LGPLv3+
# Copyright (C) 2020 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
# (michael: note that there are multiple copyright holders)

from nmigen import (Module, Signal, Cat, Repl, Mux, Const)
from nmutil.pipemodbase import PipeModBase
from nmutil.extend import exts, extz
from soc.fu.alu.pipe_data import ALUInputData, ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange


# microwatt calc_ov function.
def calc_ov(msb_a, msb_b, ca, msb_r):
    return (ca ^ msb_r) & ~(msb_a ^ msb_b)


class ALUMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return ALUInputData(self.pspec) # defines pipeline stage input format

    def ospec(self):
        return ALUOutputData(self.pspec) # defines pipeline stage output format

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        cry_o, o, cr0 = self.o.xer_ca, self.o.o, self.o.cr0
        xer_so_i, ov_o = self.i.xer_so, self.o.xer_ov
        a, b, cry_i, op = self.i.a, self.i.b, self.i.xer_ca, self.i.ctx.op

        # get L-field for OP_CMP
        x_fields = self.fields.FormX
        L = x_fields.L[0]

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)

        with m.If(op.insn_type == MicrOp.OP_CMP):
            comb += is_32bit.eq(~L)

        # little trick: do the add using only one add (not 2)
        # LSB: carry-in [0].  op/result: [1:-1].  MSB: carry-out [-1]
        add_a = Signal(a.width + 2, reset_less=True)
        add_b = Signal(a.width + 2, reset_less=True)
        add_o = Signal(a.width + 2, reset_less=True)

        a_i = Signal.like(a)
        b_i = Signal.like(b)
        with m.If(op.insn_type == MicrOp.OP_CMP): # another temporary hack
            comb += a_i.eq(a)                     # reaaaally need to move CMP
            comb += b_i.eq(b)                     # into trap pipeline
        with m.Elif(is_32bit):
            with m.If(op.is_signed):
                comb += a_i.eq(exts(a, 32, 64))
                comb += b_i.eq(exts(b, 32, 64))
            with m.Else():
                comb += a_i.eq(extz(a, 32, 64))
                comb += b_i.eq(extz(b, 32, 64))
        with m.Else():
            comb += a_i.eq(a)
            comb += b_i.eq(b)

        with m.If((op.insn_type == MicrOp.OP_ADD) |
                  (op.insn_type == MicrOp.OP_CMP)):
            # in bit 0, 1+carry_in creates carry into bit 1 and above
            comb += add_a.eq(Cat(cry_i[0], a_i, Const(0, 1)))
            comb += add_b.eq(Cat(Const(1, 1), b_i, Const(0, 1)))
            comb += add_o.eq(add_a + add_b)

        ##########################
        # main switch-statement for handling arithmetic operations

        with m.Switch(op.insn_type):

            ###################
            #### CMP, CMPL v3.0B p85-86

            with m.Case(MicrOp.OP_CMP):
                a_n = Signal(64) # temporary - inverted a
                tval = Signal(5)
                a_lt = Signal()
                carry_32 = Signal()
                carry_64 = Signal()
                zerolo = Signal()
                zerohi = Signal()
                msb_a = Signal()
                msb_b = Signal()
                newcrf = Signal(4)

                # this is supposed to be inverted (b-a, not a-b)
                comb += a_n.eq(~a) # sigh a gets inverted
                comb += carry_32.eq(add_o[33] ^ a[32] ^ b[32])
                comb += carry_64.eq(add_o[65])

                comb += zerolo.eq(~((a_n[0:32] ^ b[0:32]).bool()))
                comb += zerohi.eq(~((a_n[32:64] ^ b[32:64]).bool()))

                with m.If(zerolo & (is_32bit | zerohi)):
                    # values are equal
                    comb += tval[2].eq(1)
                with m.Else():
                    comb += msb_a.eq(Mux(is_32bit, a_n[31], a_n[63]))
                    comb += msb_b.eq(Mux(is_32bit, b[31], b[63]))
                    C0 = Const(0, 1)
                    with m.If(msb_a != msb_b):
                        # Subtraction might overflow, but
                        # comparison is clear from MSB difference.
                        # for signed, 0 is greater; for unsigned, 1 is greater
                        comb += tval.eq(Cat(msb_a, msb_b, C0, msb_b, msb_a))
                    with m.Else():
                        # Subtraction cannot overflow since MSBs are equal.
                        # carry = 1 indicates RA is smaller (signed or unsigned)
                        comb += a_lt.eq(Mux(is_32bit, carry_32, carry_64))
                        comb += tval.eq(Cat(~a_lt, a_lt, C0, ~a_lt, a_lt))
                comb += cr0.data[0:2].eq(Cat(xer_so_i[0], tval[2]))
                with m.If(op.is_signed):
                    comb += cr0.data[2:4].eq(tval[3:5])
                with m.Else():
                    comb += cr0.data[2:4].eq(tval[0:2])
                comb += cr0.ok.eq(1)

            ###################
            #### add v3.0B p67, p69-72

            with m.Case(MicrOp.OP_ADD):
                # bit 0 is not part of the result, top bit is the carry-out
                comb += o.data.eq(add_o[1:-1])
                comb += o.ok.eq(1) # output register

                # see microwatt OP_ADD code
                # https://bugs.libre-soc.org/show_bug.cgi?id=319#c5
                ca = Signal(2, reset_less=True)
                comb += ca[0].eq(add_o[-1])                   # XER.CA
                comb += ca[1].eq(add_o[33] ^ (a_i[32] ^ b_i[32])) # XER.CA32
                comb += cry_o.data.eq(ca)
                comb += cry_o.ok.eq(1)
                # 32-bit (ov[1]) and 64-bit (ov[0]) overflow
                ov = Signal(2, reset_less=True)
                comb += ov[0].eq(calc_ov(a_i[-1], b_i[-1], ca[0], add_o[-2]))
                comb += ov[1].eq(calc_ov(a_i[31], b_i[31], ca[1], add_o[32]))
                comb += ov_o.data.eq(ov)
                comb += ov_o.ok.eq(1)

            ###################
            #### exts (sign-extend) v3.0B p96, p99

            with m.Case(MicrOp.OP_EXTS):
                with m.If(op.data_len == 1):
                    comb += o.data.eq(exts(a, 8, 64))
                with m.If(op.data_len == 2):
                    comb += o.data.eq(exts(a, 16, 64))
                with m.If(op.data_len == 4):
                    comb += o.data.eq(exts(a, 32, 64))
                comb += o.ok.eq(1) # output register

            ###################
            #### cmpeqb v3.0B p88

            with m.Case(MicrOp.OP_CMPEQB):
                eqs = Signal(8, reset_less=True)
                src1 = Signal(8, reset_less=True)
                comb += src1.eq(a[0:8])
                for i in range(8):
                    comb += eqs[i].eq(src1 == b[8*i:8*(i+1)])
                comb += o.data[0].eq(eqs.any())
                comb += o.ok.eq(0) # use o.data but do *not* actually output
                comb += cr0.data.eq(Cat(Const(0, 2), eqs.any(), Const(0, 1)))
                comb += cr0.ok.eq(1)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.data.eq(xer_so_i)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
