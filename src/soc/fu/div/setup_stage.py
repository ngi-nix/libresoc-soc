# This stage is the setup stage that converts the inputs
# into the values expected by DivPipeCore

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.fu.div.pipe_data import DIVInputData
from soc.fu.alu.pipe_data import ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange
from soc.fu.div.pipe_data import CoreInputData
from ieee754.div_rem_sqrt_rsqrt.core import DivPipeCoreOperation


class DivSetupStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "setup_stage")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()
        self.abs_divisor = Signal(64)
        self.abs_dividend = Signal(64)

    def ispec(self):
        return DIVInputData(self.pspec)

    def ospec(self):
        return CoreInputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op, a, b = self.i.ctx.op, self.i.a, self.i.b
        core_o = self.o.core
        dividend_neg = self.o.dividend_neg
        divisor_neg = self.o.divisor_neg
        dividend_o = core_o.dividend
        divisor_o = core_o.divisor_radicand

        comb += core_o.operation.eq(int(DivPipeCoreOperation.UDivRem))

        comb += dividend_neg.eq(Mux(op.is_32bit, a[31], a[63]) & op.is_signed)
        comb += divisor_neg.eq(Mux(op.is_32bit, b[31], b[63]) & op.is_signed)

        # negation of a 64-bit value produces the same lower 32-bit
        # result as negation of just the lower 32-bits, so we don't
        # need to do anything special before negating
        comb += self.abs_divisor.eq(Mux(divisor_neg, -b, b))
        comb += self.abs_dividend.eq(Mux(dividend_neg, -a, a))

        comb += self.o.dive_abs_overflow_64.eq(
            (self.abs_dividend >= self.abs_divisor)
            & (op.insn_type == InternalOp.OP_DIVE))

        comb += self.o.dive_abs_overflow_32.eq(
            (self.abs_dividend[0:32] >= self.abs_divisor[0:32])
            & (op.insn_type == InternalOp.OP_DIVE))

        with m.If(op.is_32bit):
            comb += divisor_o.eq(self.abs_divisor[0:32])
        with m.Else():
            comb += divisor_o.eq(self.abs_divisor[0:64])

        comb += self.o.div_by_zero.eq(divisor_o == 0)

        ##########################
        # main switch for DIV

        with m.Switch(op.insn_type):
            with m.Case(InternalOp.OP_DIV, InternalOp.OP_MOD):
                with m.If(op.is_32bit):
                    comb += dividend_o.eq(self.abs_dividend[0:32])
                with m.Else():
                    comb += dividend_o.eq(self.abs_dividend[0:64])
            with m.Case(InternalOp.OP_DIVE):
                with m.If(op.is_32bit):
                    comb += dividend_o.eq(self.abs_dividend[0:32] << 32)
                with m.Else():
                    comb += dividend_o.eq(self.abs_dividend[0:64] << 64)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        # pass through core data

        comb += self.o.core.eq(core_o)

        return m
