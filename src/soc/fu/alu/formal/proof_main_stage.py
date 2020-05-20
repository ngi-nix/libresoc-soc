# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.fu.alu.main_stage import ALUMainStage
from soc.fu.alu.pipe_data import ALUPipeSpec
from soc.fu.alu.alu_input_record import CompALUOpSubset
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

        # convenience variables
        a = dut.i.a
        b = dut.i.b
        carry_in = dut.i.xer_ca[0]
        carry_in32 = dut.i.xer_ca[1]
        so_in = dut.i.xer_so
        carry_out = dut.o.xer_ca.data[0]
        carry_out32 = dut.o.xer_ca.data[1]
        ov_out = dut.o.xer_ov.data[0]
        ov_out32 = dut.o.xer_ov.data[1]
        o = dut.o.o

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                 carry_in.eq(AnyConst(0b11)),
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

        comb += Assume(a[32:64] == 0)
        comb += Assume(b[32:64] == 0)
        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_ADD):

                comb += Assert(Cat(o, carry_out) == (a + b + carry_in))

                # CA32 - XXX note this fails! replace with carry_in and it works
                comb += Assert((a[0:32] + b[0:32] + carry_in)[32]
                               == carry_out32)

                # From microwatt execute1.vhdl line 130
                comb += Assert(ov_out == ((carry_out ^ o[-1]) &
                                          ~(a[-1] ^ b[-1])))
                comb += Assert(ov_out32 == ((carry_out32 ^ o[31]) &
                                            ~(a[31] ^ b[31])))
            with m.Case(InternalOp.OP_EXTS):
                for i in [1, 2, 4]:
                    with m.If(rec.data_len == i):
                        comb += Assert(o[0:i*8] == a[0:i*8])
                        comb += Assert(o[i*8:64] == Repl(a[i*8-1], 64-(i*8)))
            with m.Case(InternalOp.OP_CMP):
                # CMP is defined as not taking in carry
                comb += Assume(carry_in == 0)
                comb += Assert(o == (a+b)[0:64])

            with m.Case(InternalOp.OP_CMPEQB):
                src1 = a[0:8]
                eqs = Signal(8)
                for i in range(8):
                    comb += eqs[i].eq(src1 == b[i*8:(i+1)*8])
                comb += Assert(dut.o.cr0[2] == eqs.any())

        return m


class ALUTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=2)
        self.assertFormal(module, mode="cover", depth=2)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("alu_main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
