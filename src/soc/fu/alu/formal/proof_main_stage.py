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
        # Setup random inputs for dut.op
        for p in rec.ports():
            width = p.width
            comb += p.eq(AnyConst(width))

        pspec = ALUPipeSpec(id_wid=2)
        m.submodules.dut = dut = ALUMainStage(pspec)

        # convenience variables
        a = dut.i.a
        b = dut.i.b
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
                 b.eq(AnyConst(64)),
                 ca_in.eq(AnyConst(0b11)),
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

        o_ok = Signal()
        comb += o_ok.eq(1) # will be set to zero if no op takes place

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_ADD):

                comb += Assert(Cat(o, ca_o) == (a + b + ca_in))

                # CA32 - XXX note this fails! replace with ca_in and it works
                comb += Assert((a[0:32] + b[0:32] + ca_in)[32] == ca32_o)

                # From microwatt execute1.vhdl line 130
                comb += Assert(ov_o == ((ca_o ^ o[-1]) & ~(a[-1] ^ b[-1])))
                comb += Assert(ov32_o == ((ca32_o ^ o[31]) & ~(a[31] ^ b[31])))

            with m.Case(InternalOp.OP_EXTS):
                for i in [1, 2, 4]:
                    with m.If(rec.data_len == i):
                        comb += Assert(o[0:i*8] == a[0:i*8])
                        comb += Assert(o[i*8:64] == Repl(a[i*8-1], 64-(i*8)))

            with m.Case(InternalOp.OP_CMP):
                # CMP is defined as not taking in carry
                comb += Assume(ca_in == 0)
                comb += Assert(o == (a+b)[0:64])

            with m.Case(InternalOp.OP_CMPEQB):
                src1 = a[0:8]
                eqs = Signal(8)
                for i in range(8):
                    comb += eqs[i].eq(src1 == b[i*8:(i+1)*8])
                comb += Assert(dut.o.cr0[2] == eqs.any())

            with m.Default():
                comb += o_ok.eq(0)

        # check that data ok was only enabled when op actioned
        comb += Assert(dut.o.o.ok == o_ok)

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
