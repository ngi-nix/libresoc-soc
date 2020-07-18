# Proof of correctness for trap pipeline, main stage


"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=421
"""


import unittest

from nmigen import Cat, Const, Elaboratable, Module
from nmigen.asserts import Assert, AnyConst
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase

from soc.decoder.power_enums import MicrOp

from soc.fu.trap.main_stage import TrapMainStage
from soc.fu.trap.pipe_data import TrapPipeSpec


def is_ok(sig, value):
    """
    Answers with a list of assertions that checks for valid data on
    a pipeline stage output.  sig.data must have the anticipated value,
    and sig.ok must be asserted.  The `value` is constrained to the width
    of the sig.data field it's verified against, so it's safe to add, etc.
    offsets to Nmigen signals without having to worry about inequalities from
    differing signal widths.
    """
    return [
        Assert(sig.data == value[0:len(sig.data)]),
        Assert(sig.ok),
    ]


def full_function_bits(msr):
    """
    Answers with a numeric constant signal with all "full functional"
    bits filled in, but all partial functional bits zeroed out.

    See src/soc/fu/trap/main_stage.py:msr_copy commentary for details.
    """
    zeros16_21 = Const(0, (22 - 16))
    zeros27_30 = Const(0, (31 - 27))
    return Cat(msr[0:16], zeros16_21, msr[22:27], zeros27_30, msr[31:64])


class Driver(Elaboratable):
    """
    """

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        pspec = TrapPipeSpec(id_wid=2)

        m.submodules.dut = dut = TrapMainStage(pspec)

        # frequently used aliases
        op = dut.i.ctx.op

        # start of properties
        with m.Switch(op.insn_type):
            with m.Case(MicrOp.OP_SC):
                comb += [
                    is_ok(dut.o.nia, Const(0xC00)),
                    is_ok(dut.o.srr0, dut.i.cia + 4),
                    is_ok(dut.o.srr1, full_function_bits(dut.i.msr)),
                ]

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

