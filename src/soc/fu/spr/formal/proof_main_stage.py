# Proof of correctness for SPR pipeline, main stage


"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=418
"""

from nmigen import (Elaboratable, Module)
from nmigen.asserts import Assert, AnyConst, Assume
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase

from soc.fu.spr.main_stage import SPRMainStage
from soc.fu.spr.pipe_data import SPRPipeSpec
from soc.fu.spr.spr_input_record import CompSPROpSubset
from soc.decoder.power_enums import MicrOp
import unittest


class Driver(Elaboratable):
    """
    Defines a module to drive the device under test and assert properties
    about its outputs.
    """

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # cookie-cutting most of this from alu formal proof_main_stage.py

        rec = CompSPROpSubset()
        # Setup random inputs for dut.op
        for p in rec.ports():
            width = p.width
            comb += p.eq(AnyConst(width))

        pspec = SPRPipeSpec(id_wid=2)
        m.submodules.dut = dut = SPRMainStage(pspec)

        # convenience variables
        a = dut.i.a
        ca_in = dut.i.xer_ca[0]   # CA carry in
        ca32_in = dut.i.xer_ca[1] # CA32 carry in 32
        so_in = dut.i.xer_so      # SO sticky overflow

        ca_o = dut.o.xer_ca.data[0]   # CA carry out
        ca32_o = dut.o.xer_ca.data[1] # CA32 carry out32
        ov_o = dut.o.xer_ov.data[0]   # OV overflow
        ov32_o = dut.o.xer_ov.data[1] # OV32 overflow32
        o = dut.o.o.data

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 ca_in.eq(AnyConst(0b11)),
                 so_in.eq(AnyConst(1))]

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        return m


class SPRMainStageTestCase(FHDLTestCase):
    #don't worry about it - tests are run manually anyway.  fail is fine.
    #@skipUnless(getenv("FORMAL_SPR"), "Exercise SPR formal tests [WIP]")
    def test_formal(self):
        self.assertFormal(Driver(), mode="bmc", depth=100)
        self.assertFormal(Driver(), mode="cover", depth=100)

    def test_ilang(self):
        vl = rtlil.convert(Driver(), ports=[])
        with open("spr_main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
