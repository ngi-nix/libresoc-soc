# This stage is the setup stage that converts the inputs
# into the values expected by DivPipeCore
"""
* https://bugs.libre-soc.org/show_bug.cgi?id=424
"""

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.fu.logical.pipe_data import LogicalInputData
from soc.fu.div.pipe_data import DivMulOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange
from soc.fu.div.pipe_data import CoreOutputData


class DivOutputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "output_stage")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()
        self.quotient_neg = Signal()
        self.remainder_neg = Signal()
        self.quotient_65 = Signal(65) # one extra spare bit for overflow
        self.remainder_64 = Signal(64)

    def ispec(self):
        return CoreOutputData(self.pspec)

    def ospec(self):
        return DivMulOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        op = self.i.ctx.op
        abs_quotient = self.i.core.quotient_root
        fract_width = self.pspec.core_config.fract_width
        # fract width of `DivPipeCoreOutputData.remainder`
        remainder_fract_width = fract_width * 3
        # fract width of `DivPipeCoreInputData.dividend`
        dividend_fract_width = fract_width * 2
        rem_start = remainder_fract_width - dividend_fract_width
        abs_remainder = self.i.core.remainder[rem_start:rem_start+64]
        dividend_neg = self.i.dividend_neg
        divisor_neg = self.i.divisor_neg
        quotient_65 = self.quotient_65
        remainder_64 = self.remainder_64

        # work out if sign of result is to be negative
        comb += self.quotient_neg.eq(dividend_neg ^ divisor_neg)

        # follows rules for truncating division
        comb += self.remainder_neg.eq(dividend_neg)

        # negation of a 64-bit value produces the same lower 32-bit
        # result as negation of just the lower 32-bits, so we don't
        # need to do anything special before negating
        comb += [
            quotient_65.eq(Mux(self.quotient_neg,
                               -abs_quotient, abs_quotient)),
            remainder_64.eq(Mux(self.remainder_neg,
                                -abs_remainder, abs_remainder))
        ]

        # calculate overflow
        self.o.xer_ov.ok.eq(1)
        xer_ov = self.o.xer_ov.data

        # see test_6_regression in div test_pipe_caller.py
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        def calc_overflow(dive_abs_overflow, sign_bit_mask):
            nonlocal comb
            overflow = dive_abs_overflow | self.i.div_by_zero
            ov = Signal(reset_less=True)
            with m.If(op.is_signed):
                comb += ov.eq(overflow
                                  | (abs_quotient > sign_bit_mask)
                                  | ((abs_quotient == sign_bit_mask)
                                     & ~self.quotient_neg))
            with m.Else():
                comb += ov.eq(overflow)
            comb += xer_ov.eq(Repl(ov, 2)) # set OV _and_ OV32

        # check 32/64 bit version of overflow
        with m.If(op.is_32bit):
            calc_overflow(self.i.dive_abs_ov32, 0x80000000)
        with m.Else():
            calc_overflow(self.i.dive_abs_ov64, 0x8000000000000000)

        # microwatt overflow detection
        ov = Signal(reset_less=True)
        with m.If(self.i.div_by_zero):
            comb += ov.eq(1)
        with m.Elif(~op.is_32bit):
            comb += ov.eq(self.i.dive_abs_ov64)
            with m.If(op.is_signed & (quotient_65[64] ^ quotient_65[63])):
                comb += ov.eq(1)
        with m.Elif(op.is_signed):
            comb += ov.eq(self.i.dive_abs_ov32)
            with m.If(quotient_65[32] != quotient_65[31]):
                comb += ov.eq(1)
        with m.Else():
            comb += ov.eq(self.i.dive_abs_ov32)
        comb += xer_ov.eq(Repl(ov, 2)) # set OV _and_ OV32

        ##########################
        # main switch for DIV

        o = self.o.o.data

        with m.Switch(op.insn_type):
            with m.Case(InternalOp.OP_DIVE):
                with m.If(op.is_32bit):
                    with m.If(op.is_signed):
                        # matches POWER9's divweo behavior
                        comb += o.eq(quotient_65[0:32].as_unsigned())
                    with m.Else():
                        comb += o.eq(quotient_65[0:32].as_unsigned())
                with m.Else():
                    comb += o.eq(quotient_65)
            with m.Case(InternalOp.OP_DIV):
                with m.If(op.is_32bit):
                    with m.If(op.is_signed):
                        # matches POWER9's divwo behavior
                        comb += o.eq(quotient_65[0:32].as_unsigned())
                    with m.Else():
                        comb += o.eq(quotient_65[0:32].as_unsigned())
                with m.Else():
                    comb += o.eq(quotient_65)
            with m.Case(InternalOp.OP_MOD):
                with m.If(op.is_32bit):
                    with m.If(op.is_signed):
                        # matches POWER9's modsw behavior
                        comb += o.eq(remainder_64[0:32].as_signed())
                    with m.Else():
                        comb += o.eq(remainder_64[0:32].as_unsigned())
                with m.Else():
                    comb += o.eq(remainder_64)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.data.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
