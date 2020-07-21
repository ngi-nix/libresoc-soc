# Proof of correctness for trap pipeline, main stage


"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=421
"""


import unittest

from nmigen import Cat, Const, Elaboratable, Module, Signal
from nmigen.asserts import Assert, AnyConst
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase

from soc.consts import MSR

from soc.decoder.power_enums import MicrOp

from soc.fu.trap.main_stage import TrapMainStage
from soc.fu.trap.pipe_data import TrapPipeSpec
from soc.fu.trap.trap_input_record import CompTrapOpSubset


def field(r, start, end):
    """Answers with a subfield of the signal r ("register"), where
    the start and end bits use IBM conventions.  start < end.
    """
    return r[63-end:64-start]


class Driver(Elaboratable):
    """
    """

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        rec = CompTrapOpSubset()
        pspec = TrapPipeSpec(id_wid=2)

        m.submodules.dut = dut = TrapMainStage(pspec)

        # frequently used aliases
        op = dut.i.ctx.op
        msr_o, msr_i = dut.o.msr, dut.i.msr
        srr1_o, srr1_i = dut.o.srr1, dut.i.srr1

        comb += op.eq(rec)

        # start of properties
        with m.Switch(op.insn_type):
            with m.Case(MicrOp.OP_SC):
                comb += [
                    Assert(dut.o.srr0.ok),
                    Assert(srr1_o.ok),
#                   Assert(msr_o.ok),

                    Assert(dut.o.srr0.data == (dut.i.cia + 4)[0:64]),
                    Assert(field(srr1_o, 33, 36) == 0),
                    Assert(field(srr1_o, 42, 47) == 0),
                    Assert(field(srr1_o, 0, 32) == field(msr_i, 0, 32)),
                    Assert(field(srr1_o, 37, 41) == field(msr_i, 37, 41)),
                    Assert(field(srr1_o, 48, 63) == field(msr_i, 48, 63)),

                    Assert(msr_o[0:16] == msr_i[0:16]),
                    Assert(msr_o[22:27] == msr_i[22:27]),
                    Assert(msr_o[31:64] == msr_i[31:64]),
                    Assert(msr_o[MSR.IR] == 0),  # No LPCR register input,
                    Assert(msr_o[MSR.DR] == 0),  # so assuming AIL=0.
                    Assert(msr_o[MSR.FE0] == 0),
                    Assert(msr_o[MSR.FE1] == 0),
                    Assert(msr_o[MSR.EE] == 0),
                    Assert(msr_o[MSR.RI] == 0),
                ]
                with m.If(field(op.insn, 20, 26) == 1):
                    comb += Assert(msr_o[MSR.HV] == 1)
                with m.Else():
                    comb += Assert(msr_o[MSR.HV] == 0)

            with m.Case(MicrOp.OP_RFID):
                comb += [
                    Assert(msr_o.ok),
                    Assert(dut.o.nia.ok),

                    Assert(msr_o[MSR.HV] == (srr1_i[MSR.HV] & msr_i[MSR.HV])),
                    Assert(msr_o[MSR.EE] == (srr1_i[MSR.EE] | srr1_i[MSR.PR])),
                    Assert(msr_o[MSR.IR] == (srr1_i[MSR.IR] | srr1_i[MSR.PR])),
                    Assert(msr_o[MSR.DR] == (srr1_i[MSR.DR] | srr1_i[MSR.PR])),
                    Assert(field(msr_o, 0, 2) == field(srr1_i, 0, 2)),
                    Assert(field(msr_o, 4, 28) == field(srr1_i, 4, 28)),
                    Assert(msr_o[63-32] == srr1_i[63-32]),
                    Assert(field(msr_o, 37, 41) == field(srr1_i, 37, 41)),
                    Assert(field(msr_o, 49, 50) == field(srr1_i, 49, 50)),
                    Assert(field(msr_o, 52, 57) == field(srr1_i, 52, 57)),
                    Assert(field(msr_o, 60, 63) == field(srr1_i, 60, 63)),
                    Assert(dut.o.nia.data == Cat(Const(0, 2), dut.i.srr0[2:])),
                ]
                with m.If(msr_i[MSR.HV]):
                    comb += Assert(msr_o[MSR.ME] == srr1_i[MSR.ME])
                with m.Else():
                    comb += Assert(msr_o[MSR.ME] == msr_i[MSR.ME])
                with m.If((field(msr_i , 29, 31) != 0b010) | # MSR
                          (field(srr1_i, 29, 31) != 0b000)): # SRR1
                    comb += Assert(field(msr_o.data, 29, 31) ==
                                   field(srr1_i, 29, 31))
                with m.Else():
                    comb += Assert(field(msr_o.data, 29, 31) ==
                                   field(msr_i, 29, 31))

        comb += dut.i.ctx.matches(dut.o.ctx)

        return m


class TrapMainStageTestCase(FHDLTestCase):
    def test_formal(self):
        self.assertFormal(Driver(), mode="bmc", depth=10)
        self.assertFormal(Driver(), mode="cover", depth=10)

    def test_ilang(self):
        vl = rtlil.convert(Driver(), ports=[])
        with open("trap_main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()

