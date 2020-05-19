
from nmigen import (Module, Signal, Cat, Repl, Mux, Const, signed)
from nmutil.pipemodbase import PipeModBase
from soc.fu.trap.pipe_data import TrapInputData, TrapOutputData
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange


class TrapMainStage(PipeModBase):
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

        # take copy of D-Form TO field
        i_fields = self.fields.FormD
        to = Signal(i_fields.TO[0:-1].shape())
        comb += to.eq(i_fields.TO[0:-1])

        # signed/unsigned temporaries for RA and RB
        a_s = Signal(signed(64), reset_less=True)
        b_s = Signal(signed(64), reset_less=True)

        a = Signal(64, reset_less=True)
        b = Signal(64, reset_less=True)

        # set up A and B comparison (truncate/sign-extend if 32 bit)
        with m.If(op.is_32bit):
            comb += a_s.eq(self.i.a[0:32], Repl(self.i.a[32], 32))
            comb += b_s.eq(self.i.b[0:32], Repl(self.i.b[32], 32))
            comb += a.eq(self.i.a[0:32])
            comb += b.eq(self.i.b[0:32])
        with m.Else():
            comb += a_s.eq(self.i.a)
            comb += b_s.eq(self.i.b)
            comb += a.eq(self.i.a)
            comb += b.eq(self.i.b)

        # establish comparison bits
        lt_s = Signal(reset_less=True)
        gt_s = Signal(reset_less=True)
        lt_u = Signal(reset_less=True)
        gt_u = Signal(reset_less=True)
        equal = Signal(reset_less=True)

        comb += lt_s.eq(a_s < b_s)
        comb += gt_s.eq(a_s > b_s)
        comb += lt_u.eq(a < b)
        comb += gt_u.eq(a > b)
        comb += equal.eq(a == b)

        # They're in reverse bit order because POWER. Check Book 1,
        # Appendix C.6 for chart
        trap_bits = Signal(5)
        comb += trap_bits.eq(Cat(gt_u, lt_u, equal, gt_s, lt_s))

        # establish if the trap should go ahead (any tests requested in TO)
        should_trap = Signal()
        comb += should_trap.eq((trap_bits & to).any())

        # TODO: some #defines for the bits n stuff.
        with m.Switch(op):
            with m.Case(InternalOp.OP_TRAP):
                with m.If(should_trap):
                    comb += self.o.nia.data.eq(0x700)         # trap address
                    comb += self.o.nia.ok.eq(1)
                    comb += self.o.srr1.data.eq(self.i.msr)   # old MSR
                    comb += self.o.srr1[63-46].eq(1)     # XXX which bit?
                    comb += self.o.srr1.ok.eq(1)
                    comb += self.o.srr0.data.eq(self.i.cia)   # old PC
                    comb += self.o.srr0.ok.eq(1)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
