
from nmigen import (Module, Signal, Cat, Repl, Mux, Const, signed)
from nmutil.pipemodbase import PipeModBase
from nmutil.clz import CLZ
from soc.fu.trap.pipe_data import TrapInputData, TrapOutputData
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange


def array_of(count, bitwidth):
    res = []
    for i in range(count):
        res.append(Signal(bitwidth, reset_less=True))
    return res


class LogicalMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return TrapInputData(self.pspec)

    def ospec(self):
        return TrapOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op

        i_fields = self.fields.FormD
        to = Signal(i_fields.TO[0:-1].shape())
        comb += to.eq(i_fields.TO[0:-1])

        a_signed = Signal(signed(64), reset_less=True)
        b_signed = Signal(signed(64), reset_less=True)

        a = Signal(64, reset_less=True)
        b = Signal(64, reset_less=True)

        with m.If(self.i.ctx.op.is_32bit):
            comb += a_signed.eq(self.i.a[0:32],
                                Repl(self.i.a[32], 32))
            comb += b_signed.eq(self.i.b[0:32],
                                Repl(self.i.b[32], 32))
            comb += a.eq(self.i.a[0:32])
            comb += b.eq(self.i.b[0:32])
        with m.Else():
            comb += a_signed.eq(self.i.a)
            comb += b_signed.eq(self.i.b)
            comb += a.eq(self.i.a)
            comb += b.eq(self.i.b)

        lt_signed = Signal()
        gt_signed = Signal()
        lt_unsigned = Signal()
        gt_unsigned = Signal()
        equal = Signal()

        comb += lt_signed.eq(a_signed < b_signed)
        comb += gt_signed.eq(a_signed > b_signed)
        comb += lt_unsigned.eq(a < b)
        comb += gt_unsigned.eq(a > b)
        comb += equal.eq(a == b)

        trap_bits = Signal(5)
        # They're in reverse bit order because POWER. Check Book 1,
        # Appendix C.6 for chart
        comb += trap_bits.eq(Cat(gt_unsigned, lt_unsigned, equal,
                                 gt_signed, lt_signed))
        should_trap = Signal()
        comb += should_trap.eq((trap_bits & to).any())
            
        with m.Switch(op):
            with m.Case(InternalOp.OP_TRAP):
                pass


        comb += self.o.ctx.eq(self.i.ctx)

        return m
