# Proof of correctness for Condition Register pipeline
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

        pspec = ALUPipeSpec(id_wid=2)
        m.submodules.dut = dut = CRMainStage(pspec)

        full_cr_in = Signal(32)
        cr_a_in = Signal(4)

        cr_o = Signal(32)

        a = dut.i.a
        b = dut.i.b
        cr = full_cr_in
        full_cr_out = dut.o.full_cr
        o = dut.o.o

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                 cr_a_in.eq(AnyConst(4)),
                 full_cr_in.eq(AnyConst(32))]

        a_fields = dut.fields.FormA
        xl_fields = dut.fields.FormXL
        xfx_fields = dut.fields.FormXFX

        # I'd like to be able to prove this module using the proof
        # written before I made the change to use 4 bit cr inputs for
        # OP_MCRF and OP_CROP. So I'm going to set up the machinery to
        # let me do that here

        cr_input_arr = Array([full_cr_in[(7-i)*4:(7-i)*4+4] for i in range(8)])
        cr_output_arr = Array([cr_o[(7-i)*4:(7-i)*4+4] for i in range(8)])

        with m.Switch(rec.insn_type):
            # CR_ISEL takes cr_a
            with m.Case(InternalOp.OP_ISEL):
                comb += dut.i.cr_a.eq(cr_a_in)

            # For OP_CROP, we need to input the corresponding CR
            # registers for BA, BB, and BT
            with m.Case(InternalOp.OP_CROP):
                # grab the MSBs of the 3 bit selectors
                bt = Signal(3, reset_less=True)
                ba = Signal(3, reset_less=True)
                bb = Signal(3, reset_less=True)
                comb += bt.eq(xl_fields.BT[2:5])
                comb += ba.eq(xl_fields.BA[2:5])
                comb += bb.eq(xl_fields.BB[2:5])

                # Grab the cr register containing the bit from BA, BB,
                # and BT, and feed it to the cr inputs
                comb += dut.i.cr_a.eq(cr_input_arr[ba])
                comb += dut.i.cr_b.eq(cr_input_arr[bb])
                comb += dut.i.cr_c.eq(cr_input_arr[bt])

                # Insert the output into the output CR register so the
                # proof below can use it
                for i in range(8):
                    with m.If(i != bt):
                        comb += cr_output_arr[i].eq(cr_input_arr[i])
                    with m.Else():
                        comb += cr_output_arr[i].eq(dut.o.cr_o)

            with m.Case(InternalOp.OP_MCRF):
                # This does a similar thing to OP_CROP above, with
                # less inputs. The CR selection fields are already 3
                # bits so there's no need to grab only the MSBs
                bf = Signal(xl_fields.BF[0:-1].shape())
                bfa = Signal(xl_fields.BFA[0:-1].shape())
                comb += bf.eq(xl_fields.BF[0:-1])
                comb += bfa.eq(xl_fields.BFA[0:-1])

                # set cr_a to the CR selected by BFA
                comb += dut.i.cr_a.eq(cr_input_arr[bfa])
                for i in range(8):
                    # Similar to above, insert the result cr back into
                    # the full cr register so the proof below can use
                    # it
                    with m.If(i != bf):
                        comb += cr_output_arr[i].eq(cr_input_arr[i])
                    with m.Else():
                        comb += cr_output_arr[i].eq(dut.o.cr_o)

            # For the other two, they take the full CR as input, and
            # output a full CR. This handles that
            with m.Default():
                comb += dut.i.full_cr.eq(full_cr_in)
                comb += cr_o.eq(dut.o.full_cr)

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        # big endian indexing. *sigh*
        cr_arr = Array([cr[31-i] for i in range(32)])
        cr_o_arr = Array([cr_o[31-i] for i in range(32)])

        FXM = xfx_fields.FXM[0:-1]
        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_MTCRF):
                for i in range(8):
                    with m.If(FXM[i]):
                        comb += Assert(cr_o[4*i:4*i+4] == a[4*i:4*i+4])
            with m.Case(InternalOp.OP_MFCR):
                with m.If(rec.insn[20]):  # mfocrf
                    for i in range(8):
                        with m.If(FXM[i]):
                            comb += Assert(o[4*i:4*i+4] == cr[4*i:4*i+4])
                        with m.Else():
                            comb += Assert(o[4*i:4*i+4] == 0)
                with m.Else(): # mfcrf
                    comb += Assert(o == cr)
            with m.Case(InternalOp.OP_MCRF):
                BF = xl_fields.BF[0:-1]
                BFA = xl_fields.BFA[0:-1]
                for i in range(4):
                    comb += Assert(cr_o_arr[BF*4+i] == cr_arr[BFA*4+i])
                for i in range(8):
                    with m.If(BF != 7-i):
                        comb += Assert(cr_o[i*4:i*4+4] == cr[i*4:i*4+4])

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

            with m.Case(InternalOp.OP_ISEL):
                # just like in branch, CR0-7 is incoming into cr_a, we
                # need to select from the last 2 bits of BC
                BC = a_fields.BC[0:-1][0:2]
                cr_bits = Array([cr_a_in[3-i] for i in range(4)])

                # The bit of (cr_a=CR0-7) selected by BC
                cr_bit = Signal(reset_less=True)
                comb += cr_bit.eq(cr_bits[BC])

                # select a or b as output
                comb += Assert(o == Mux(cr_bit, a, b))

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
