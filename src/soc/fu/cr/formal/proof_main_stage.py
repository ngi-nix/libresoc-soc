# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=332
"""

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, Array)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.fu.cr.main_stage import CRMainStage
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
        m.submodules.dut = dut = CRMainStage(pspec)

        a = dut.i.a
        cr = dut.i.cr
        cr_o = dut.o.cr

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 cr.eq(AnyConst(64))]

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        # big endian indexing. *sigh*
        cr_arr = Array([cr[31-i] for i in range(32)])
        cr_o_arr = Array([cr_o[31-i] for i in range(32)])

        xl_fields = dut.fields.FormXL
        xfx_fields = dut.fields.FormXFX
        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_MTCRF):
                FXM = xfx_fields.FXM[0:-1]
                for i in range(8):
                    with m.If(FXM[i]):
                        comb += Assert(cr_o[4*i:4*i+4] == a[4*i:4*i+4])
            with m.Case(InternalOp.OP_CROP):
                bt = Signal(xl_fields.BT[0:-1].shape(), reset_less=True)
                ba = Signal(xl_fields.BA[0:-1].shape(), reset_less=True)
                bb = Signal(xl_fields.BB[0:-1].shape(), reset_less=True)
                comb += bt.eq(xl_fields.BT[0:-1])
                comb += ba.eq(xl_fields.BA[0:-1])
                comb += bb.eq(xl_fields.BB[0:-1])

                bit_a = Signal()
                bit_b = Signal()
                bit_o = Signal()
                comb += bit_a.eq(cr_arr[ba])
                comb += bit_b.eq(cr_arr[bb])
                comb += bit_o.eq(cr_o_arr[bt])

                lut = Signal(4)
                comb += lut.eq(rec.insn[6:10])
                with m.If(lut == 0b1000):
                    comb += Assert(bit_o == bit_a & bit_b)
                with m.If(lut == 0b0100):
                    comb += Assert(bit_o == bit_a & ~bit_b)
                with m.If(lut == 0b1001):
                    comb += Assert(bit_o == ~(bit_a ^ bit_b))
                with m.If(lut == 0b0111):
                    comb += Assert(bit_o == ~(bit_a & bit_b))
                with m.If(lut == 0b0001):
                    comb += Assert(bit_o == ~(bit_a | bit_b))
                with m.If(lut == 0b1110):
                    comb += Assert(bit_o == bit_a | bit_b)
                with m.If(lut == 0b1101):
                    comb += Assert(bit_o == bit_a | ~bit_b)
                with m.If(lut == 0b0110):
                    comb += Assert(bit_o == bit_a ^ bit_b)

        return m


class CRTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=2)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("cr_main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
