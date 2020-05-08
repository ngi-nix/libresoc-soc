# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import Module, Signal, Elaboratable, Mux
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.alu.input_stage import ALUInputStage
from soc.alu.pipe_data import ALUPipeSpec
from soc.alu.alu_input_record import CompALUOpSubset
import unittest


# This defines a module to drive the device under test and assert
# properties about its outputs
class Driver(Elaboratable):
    def __init__(self):
        # inputs and outputs
        pass

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        pspec = ALUPipeSpec()
        m.submodules.dut = dut = ALUInputStage(pspec)

        rec = CompALUOpSubset()

        for p in rec.ports():
            width = p.width
            comb += p.eq(AnyConst(width))

        comb += dut.i.op.eq(rec)

        for p in rec.ports():
            name = p.name
            rec_sig = p
            dut_sig = getattr(dut.o.op, name)
            comb += Assert(dut_sig == rec_sig)


        return m

class GTCombinerTestCase(FHDLTestCase):
    def test_gt_combiner(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)
        self.assertFormal(module, mode="cover", depth=4)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("input_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
