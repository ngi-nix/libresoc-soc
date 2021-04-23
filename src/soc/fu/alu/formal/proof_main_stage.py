# Proof of correctness for ALU pipeline, main stage
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=306
* https://bugs.libre-soc.org/show_bug.cgi?id=305
* https://bugs.libre-soc.org/show_bug.cgi?id=343
"""

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil

from soc.fu.alu.main_stage import ALUMainStage
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

        # and for the context muxid
        width = dut.i.ctx.muxid.width
        comb += dut.i.ctx.muxid.eq(AnyConst(width))

        # assign the PowerDecode2 operation subset
        comb += dut.i.ctx.op.eq(rec)

        # check that the operation (op) is passed through (and muxid)
        comb += Assert(dut.o.ctx.op == dut.i.ctx.op)
        comb += Assert(dut.o.ctx.muxid == dut.i.ctx.muxid)

        # signed and signed/32 versions of input a
        a_signed = Signal(signed(64))
        a_signed_32 = Signal(signed(32))
        comb += a_signed.eq(a)
        comb += a_signed_32.eq(a[0:32])

        # do not check MSBs of a/b in 32-bit mode
        with m.If(rec.is_32bit):
            comb += Assume(a[32:64] == 0)
            comb += Assume(b[32:64] == 0)

        # Data.ok checking.  these only to be valid when there is a change
        # in the output that needs to go into a regfile
        o_ok = Signal()
        cr0_ok = Signal()
        ov_ok = Signal()
        ca_ok = Signal()
        comb += cr0_ok.eq(0)
        comb += ov_ok.eq(0)
        comb += ca_ok.eq(0)

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(MicrOp.OP_ADD):

                # check result of 65-bit add-with-carry
                comb += Assert(Cat(o, ca_o) == (a + b + ca_in))

                # CA32 - XXX note this fails! replace with ca_in and it works
                comb += Assert((a[0:32] + b[0:32] + ca_in)[32] == ca32_o)

                # From microwatt execute1.vhdl line 130, calc_ov() function
                comb += Assert(ov_o == ((ca_o ^ o[-1]) & ~(a[-1] ^ b[-1])))
                comb += Assert(ov32_o == ((ca32_o ^ o[31]) & ~(a[31] ^ b[31])))
                comb += ov_ok.eq(1)
                comb += ca_ok.eq(1)
                comb += o_ok.eq(1)

            with m.Case(MicrOp.OP_EXTS):
                for i in [1, 2, 4]:
                    with m.If(rec.data_len == i):
                        # main part, then sign-bit replicated up
                        comb += Assert(o[0:i*8] == a[0:i*8])
                        comb += Assert(o[i*8:64] == Repl(a[i*8-1], 64-(i*8)))
                comb += o_ok.eq(1)

            with m.Case(MicrOp.OP_CMP):
                # CMP is defined as not taking in carry
                comb += Assume(ca_in == 0)
                comb += Assert(o == (a+b)[0:64])

            with m.Case(MicrOp.OP_CMPEQB):
                src1 = a[0:8]
                eqs = Signal(8)
                for i in range(8):
                    comb += eqs[i].eq(src1 == b[i*8:(i+1)*8])
                comb += Assert(dut.o.cr0.data[2] == eqs.any())
                comb += cr0_ok.eq(1)

        # check that data ok was only enabled when op actioned
        comb += Assert(dut.o.o.ok == o_ok)
        comb += Assert(dut.o.cr0.ok == cr0_ok)
        comb += Assert(dut.o.xer_ov.ok == ov_ok)
        comb += Assert(dut.o.xer_ca.ok == ca_ok)

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
