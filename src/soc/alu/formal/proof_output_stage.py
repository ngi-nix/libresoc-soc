# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import Module, Signal, Elaboratable, Mux, Cat, signed
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.alu.output_stage import ALUOutputStage
from soc.alu.pipe_data import ALUPipeSpec
from soc.alu.alu_input_record import CompALUOpSubset
from soc.decoder.power_enums import InternalOp
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
        m.submodules.dut = dut = ALUOutputStage(pspec)

        o = Signal(64)
        carry_out = Signal()
        carry_out32 = Signal()
        ov = Signal()
        ov32 = Signal()
        cr0 = Signal(4)
        so = Signal()
        comb += [dut.i.o.eq(o),
                 dut.i.carry_out.eq(carry_out),
                 dut.i.so.eq(so),
                 dut.i.carry_out32.eq(carry_out32),
                 dut.i.cr0.eq(cr0),
                 dut.i.ov.eq(ov),
                 dut.i.ov32.eq(ov32),
                 o.eq(AnyConst(64)),
                 carry_out.eq(AnyConst(1)),
                 carry_out32.eq(AnyConst(1)),
                 ov.eq(AnyConst(1)),
                 ov32.eq(AnyConst(1)),
                 cr0.eq(AnyConst(4)),
                 so.eq(AnyConst(1))]

        comb += dut.i.ctx.op.eq(rec)

        with m.If(dut.i.ctx.op.invert_out):
            comb += Assert(dut.o.o == ~o)
        with m.Else():
            comb += Assert(dut.o.o == o)

        cr_out = Signal.like(cr0)
        comb += cr_out.eq(dut.o.cr0)

        o_signed = Signal(signed(64))
        comb += o_signed.eq(dut.o.o)
        # Assert only one of the comparison bits is set
        comb += Assert(cr_out[0] + cr_out[1] + cr_out[2] == 1)
        with m.If(o_signed == 0):
            comb += Assert(cr_out[2] == 1)
        with m.Elif(o_signed > 0):
            comb += Assert(cr_out[1] == 1)
        with m.Elif(o_signed < 0):
            comb += Assert(cr_out[0] == 1)


        # Assert that op gets copied from the input to output
        for p in rec.ports():
            name = p.name
            rec_sig = p
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)


        return m

class GTCombinerTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)
        self.assertFormal(module, mode="cover", depth=4)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("output_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
