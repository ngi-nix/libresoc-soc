# This stage is the setup stage that converts the inputs
# into the values expected by DivPipeCore

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.fu.logical.pipe_data import LogicalInputData
from soc.fu.alu.pipe_data import ALUOutputData
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
        self.quotient_64 = Signal(64)
        self.remainder_64 = Signal(64)

    def ispec(self):
        return CoreOutputData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
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
        quotient_64 = self.quotient_64
        remainder_64 = self.remainder_64

        comb += self.quotient_neg.eq(dividend_neg ^ divisor_neg)
        # follows rules for truncating division
        comb += self.remainder_neg.eq(dividend_neg)

        # negation of a 64-bit value produces the same lower 32-bit
        # result as negation of just the lower 32-bits, so we don't
        # need to do anything special before negating
        comb += [
            quotient_64.eq(Mux(self.quotient_neg,
                               -abs_quotient, abs_quotient)),
            remainder_64.eq(Mux(self.remainder_neg,
                                -abs_remainder, abs_remainder))
        ]

        xer_ov = self.o.xer_ov.data

        # TODO(programmerjake): check code against instruction models

        def calc_overflow(dive_abs_overflow, sign_bit_mask):
            nonlocal comb
            overflow = dive_abs_overflow | self.i.div_by_zero
            with m.If(op.is_signed):
                comb += xer_ov.eq(overflow
                                  | (abs_quotient > sign_bit_mask)
                                  | ((abs_quotient == sign_bit_mask)
                                     & ~self.quotient_neg))
            with m.Else():
                comb += xer_ov.eq(overflow)

        with m.If(op.is_32bit):
            calc_overflow(self.i.dive_abs_overflow_32, 0x8000_0000)
        with m.Else():
            calc_overflow(self.i.dive_abs_overflow_32, 0x8000_0000_0000_0000)

        ##########################
        # main switch for DIV

        with m.Switch(op.insn_type):
            # TODO(programmerjake): finish switch
            with m.Case(InternalOp.OP_DIV, InternalOp.OP_DIVE):
                with m.If(op.is_32bit):
                    comb += dividend_in.eq(self.abs_dividend[0:32])
                with m.Else():
                    comb += dividend_in.eq(self.abs_dividend[0:64])
            with m.Case(InternalOp.OP_MOD):
                with m.If(op.is_32bit):
                    comb += dividend_in.eq(self.abs_dividend[0:32] << 32)
                with m.Else():
                    comb += dividend_in.eq(self.abs_dividend[0:64] << 64)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.data.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
