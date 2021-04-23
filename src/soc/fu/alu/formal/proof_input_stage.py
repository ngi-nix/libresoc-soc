# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import Module, Signal, Elaboratable, Mux
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil

from soc.fu.alu.input_stage import ALUInputStage
from soc.fu.alu.pipe_data import ALUPipeSpec
from soc.fu.alu.alu_input_record import CompALUOpSubset
from openpower.decoder.power_enums import MicrOp
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

        rec = CompALUOpSubset()
        recwidth = 0
        # Setup random inputs for dut.op
        for p in rec.ports():
            width = p.width
            recwidth += width
            comb += p.eq(AnyConst(width))

        pspec = ALUPipeSpec(id_wid=2, op_wid=recwidth)
        m.submodules.dut = dut = ALUInputStage(pspec)

        a = Signal(64)
        b = Signal(64)
        comb += [dut.i.a.eq(a),
                 dut.i.b.eq(b),
                 a.eq(AnyConst(64)),
                 b.eq(AnyConst(64))]

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for p in rec.ports():
            name = p.name
            rec_sig = p
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        with m.If(rec.invert_in):
            comb += Assert(dut.o.a == ~a)
        with m.Else():
            comb += Assert(dut.o.a == a)

        comb += Assert(dut.o.b == b)

        return m


class GTCombinerTestCase(FHDLTestCase):
    def test_formal(self):
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
