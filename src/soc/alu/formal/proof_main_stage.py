# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.alu.main_stage import ALUMainStage
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
        m.submodules.dut = dut = ALUMainStage(pspec)

        a = Signal(64)
        b = Signal(64)
        carry_in = Signal()
        so_in = Signal()
        comb += [dut.i.a.eq(a),
                 dut.i.b.eq(b),
                 dut.i.carry_in.eq(carry_in),
                 dut.i.so.eq(so_in),
                 a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                 carry_in.eq(AnyConst(1)),
                 so_in.eq(AnyConst(1))]
                      

        comb += dut.i.ctx.op.eq(rec)


        # Assert that op gets copied from the input to output
        for p in rec.ports():
            name = p.name
            rec_sig = p
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        a_signed = Signal(signed(64))
        comb += a_signed.eq(a)
        a_signed_32 = Signal(signed(32))
        comb += a_signed_32.eq(a[0:32])

        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_ADD):
                comb += Assert(Cat(dut.o.o, dut.o.carry_out) ==
                               (a + b + carry_in))
            with m.Case(InternalOp.OP_AND):
                comb += Assert(dut.o.o == a & b)
            with m.Case(InternalOp.OP_OR):
                comb += Assert(dut.o.o == a | b)
            with m.Case(InternalOp.OP_XOR):
                comb += Assert(dut.o.o == a ^ b)
            with m.Case(InternalOp.OP_SHL):
                with m.If(rec.is_32bit):
                    comb += Assert(dut.o.o[0:32] == ((a << b[0:6]) &
                                                     0xffffffff))
                    comb += Assert(dut.o.o[32:64] == 0)
                with m.Else():
                    comb += Assert(dut.o.o == ((a << b[0:7]) &
                                               ((1 << 64)-1)))
            with m.Case(InternalOp.OP_SHR):
                with m.If(~rec.is_signed):
                    with m.If(rec.is_32bit):
                        comb += Assert(dut.o.o[0:32] ==
                                       (a[0:32] >> b[0:6]))
                        comb += Assert(dut.o.o[32:64] == 0)
                    with m.Else():
                        comb += Assert(dut.o.o == (a >> b[0:7]))
                with m.Else():
                    with m.If(rec.is_32bit):
                        comb += Assert(dut.o.o[0:32] ==
                                       (a_signed_32 >> b[0:6]))
                        comb += Assert(dut.o.o[32:64] == Repl(a[31], 32))
                    with m.Else():
                        comb += Assert(dut.o.o == (a_signed >> b[0:7]))


        return m

class GTCombinerTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)
        self.assertFormal(module, mode="cover", depth=4)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
