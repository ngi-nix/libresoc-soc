# This stage is the setup stage that converts the inputs
# into the values expected by DivPipeCore

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.fu.div.pipe_data import DivInputData
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange
from soc.fu.div.pipe_data import CoreInputData
from ieee754.div_rem_sqrt_rsqrt.core import DivPipeCoreOperation
from nmutil.util import eq32


class DivSetupStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "setup_stage")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return DivInputData(self.pspec)

    def ospec(self):
        return CoreInputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        # convenience variables
        op, a, b = self.i.ctx.op, self.i.a, self.i.b
        core_o = self.o.core
        dividend_neg_o = self.o.dividend_neg
        divisor_neg_o = self.o.divisor_neg
        dividend_o = core_o.dividend
        divisor_o = core_o.divisor_radicand

        # set operation to unsigned div/remainder
        comb += core_o.operation.eq(int(DivPipeCoreOperation.UDivRem))

        # work out if a/b are negative (check 32-bit / signed)
        comb += dividend_neg_o.eq(Mux(op.is_32bit,
                                      a[31], a[63]) & op.is_signed)
        comb += divisor_neg_o.eq(Mux(op.is_32bit, b[31], b[63]) & op.is_signed)

        # negation of a 64-bit value produces the same lower 32-bit
        # result as negation of just the lower 32-bits, so we don't
        # need to do anything special before negating
        abs_dor = Signal(64, reset_less=True)  # absolute of divisor
        abs_dend = Signal(64, reset_less=True)  # absolute of dividend
        comb += abs_dor.eq(Mux(divisor_neg_o, -b, b))
        comb += abs_dend.eq(Mux(dividend_neg_o, -a, a))

        # check for absolute overflow condition (32/64)
        comb += self.o.dive_abs_ov64.eq((abs_dend >= abs_dor)
                                        & (op.insn_type == MicrOp.OP_DIVE))

        comb += self.o.dive_abs_ov32.eq((abs_dend[0:32] >= abs_dor[0:32])
                                        & (op.insn_type == MicrOp.OP_DIVE))

        # set divisor based on 32/64 bit mode (must be absolute)
        comb += eq32(op.is_32bit, divisor_o, abs_dor)

        # divide by zero error detection
        comb += self.o.div_by_zero.eq(divisor_o == 0)

        ##########################
        # main switch for Div

        with m.Switch(op.insn_type):
            # div/mod takes straight (absolute) dividend
            with m.Case(MicrOp.OP_DIV, MicrOp.OP_MOD):
                comb += eq32(op.is_32bit, dividend_o, abs_dend)
            # extended div shifts dividend up
            with m.Case(MicrOp.OP_DIVE):
                with m.If(op.is_32bit):
                    comb += dividend_o.eq(abs_dend[0:32] << 32)
                with m.Else():
                    comb += dividend_o.eq(abs_dend[0:64] << 64)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
