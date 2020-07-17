# Proof of correctness for trap pipeline, main stage


"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=421
"""


import unittest

from nmigen import Elaboratable, Module
from nmigen.asserts import Assert, AnyConst
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase

from soc.fu.trap.main_stage import TrapMainStage
from soc.fu.trap.pipe_data import TrapPipeSpec


class Driver(Elaboratable):
    """
    """

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        pspec = TrapPipeSpec(id_wid=2)

        m.submodules.dut = dut = TrapMainStage(pspec)

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

