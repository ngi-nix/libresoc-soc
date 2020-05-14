# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.shift_rot.main_stage import ShiftRotMainStage
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
        m.submodules.dut = dut = ShiftRotMainStage(pspec)

        # convenience variables
        a = dut.i.rs
        b = dut.i.rb
        ra = dut.i.ra
        carry_in = dut.i.carry_in
        so_in = dut.i.so
        carry_out = dut.o.carry_out
        o = dut.o.o

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                 carry_in.eq(AnyConst(1)),
                 so_in.eq(AnyConst(1))]

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        # signed and signed/32 versions of input a
        a_signed = Signal(signed(64))
        a_signed_32 = Signal(signed(32))
        comb += a_signed.eq(a)
        comb += a_signed_32.eq(a[0:32])

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_SHL):
                comb += Assume(ra == 0)
                with m.If(rec.is_32bit):
                    comb += Assert(o[0:32] == ((a << b[0:6]) & 0xffffffff))
                    comb += Assert(o[32:64] == 0)
                with m.Else():
                    comb += Assert(o == ((a << b[0:7]) & ((1 << 64)-1)))
            with m.Case(InternalOp.OP_SHR):
                comb += Assume(ra == 0)
                with m.If(~rec.is_signed):
                    with m.If(rec.is_32bit):
                        comb += Assert(o[0:32] == (a[0:32] >> b[0:6]))
                        comb += Assert(o[32:64] == 0)
                    with m.Else():
                        comb += Assert(o == (a >> b[0:7]))
                with m.Else():
                    with m.If(rec.is_32bit):
                        comb += Assert(o[0:32] == (a_signed_32 >> b[0:6]))
                        comb += Assert(o[32:64] == Repl(a[31], 32))
                    with m.Else():
                        comb += Assert(o == (a_signed >> b[0:7]))

        return m


class ALUTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=2)
        self.assertFormal(module, mode="cover", depth=2)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
