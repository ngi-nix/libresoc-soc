# Proof of correctness for SPR pipeline, main stage


"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=418
"""

from os import getenv

from unittest import skipUnless

from nmigen import (Elaboratable, Module)
from nmigen.asserts import Assert
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase

from soc.fu.spr.main_stage import SPRMainStage
from soc.fu.spr.pipe_data import SPRPipeSpec


class Driver(Elaboratable):
    """
    Defines a module to drive the device under test and assert properties
    about its outputs.
    """

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        dut = SPRMainStage(SPRPipeSpec(id_wid=2))

        # Output context is the same as the input context.
        comb += Assert(dut.o.ctx != dut.i.ctx)

        return m


class SPRMainStageTestCase(FHDLTestCase):
    @skipUnless(getenv("FORMAL_SPR"), "Exercise SPR formal tests [WIP]")
    def test_formal(self):
        self.assertFormal(Driver(), mode="bmc", depth=100)
        self.assertFormal(Driver(), mode="cover", depth=100)

    def test_ilang(self):
        vl = rtlil.convert(Driver(), ports=[])
        with open("spr_main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
