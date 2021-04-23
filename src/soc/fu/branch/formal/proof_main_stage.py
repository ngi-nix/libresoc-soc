# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=335
* https://libre-soc.org/openpower/isa/branch/
"""

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, Array, Const)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmutil.extend import exts
from nmigen.cli import rtlil

from soc.fu.branch.main_stage import BranchMainStage
from soc.fu.branch.pipe_data import BranchPipeSpec
from soc.fu.branch.br_input_record import CompBROpSubset
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

        rec = CompBROpSubset()
        recwidth = 0
        # Setup random inputs for dut.op
        for p in rec.ports():
            width = p.width
            recwidth += width
            comb += p.eq(AnyConst(width))

        pspec = BranchPipeSpec(id_wid=2)
        m.submodules.dut = dut = BranchMainStage(pspec)

        # convenience aliases
        op = dut.i.ctx.op
        cia, cr_in, fast1, fast2 = op.cia, dut.i.cr, dut.i.fast1, dut.i.fast2
        ctr = fast1
        lr_o, nia_o = dut.o.lr, dut.o.nia

        comb += op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(op, name)
            comb += Assert(dut_sig == rec_sig)

        # Full width CR register. Will have bitfield extracted for
        # feeding to branch unit
        cr = Signal(32)
        comb += cr.eq(AnyConst(32))
        cr_arr = Array([cr[(7-i)*4:(7-i)*4+4] for i in range(8)])
        cr_bit_arr = Array([cr[31-i] for i in range(32)])

        comb += fast2.eq(AnyConst(64))
        comb += ctr.eq(AnyConst(64))

        i_fields = dut.fields.FormI
        b_fields = dut.fields.FormB
        xl_fields = dut.fields.FormXL

        # absolute address mode
        AA = i_fields.AA[0:-1]

        # Handle CR bit selection
        BI = b_fields.BI[0:-1]
        bi = Signal(3, reset_less=True)
        comb += bi.eq(BI[2:5])
        comb += dut.i.cr.eq(cr_arr[bi])

        # Handle branch out
        BO = b_fields.BO[0:-1]
        bo = Signal(BO.shape())
        comb += bo.eq(BO)
        cond_ok = Signal()

        # handle conditional
        XO = xl_fields.XO[0:-1]
        xo = Signal(XO.shape())
        comb += xo.eq(XO)

        # Check CR according to BO
        comb += cond_ok.eq(bo[4] | (cr_bit_arr[BI] == bo[3]))

        # CTR decrement
        ctr_next = Signal.like(ctr)
        with m.If(~BO[2]):
            comb += ctr_next.eq(ctr - 1)
        with m.Else():
            comb += ctr_next.eq(ctr)

        # 32/64 bit CTR
        ctr_m = Signal.like(ctr)
        with m.If(rec.is_32bit):
            comb += ctr_m.eq(ctr[:32])
        with m.Else():
            comb += ctr_m.eq(ctr)

        # CTR (32/64 bit) compare with 0
        ctr_ok = Signal()
        comb += ctr_ok.eq(BO[2] | ((ctr_m != 0) ^ BO[1]))

        with m.Switch(rec.insn_type):

            ###
            # b - v3.0B p37
            ###
            with m.Case(MicrOp.OP_B):
                # Extract target address
                LI = i_fields.LI[0:-1]
                imm = exts(LI, LI.shape().width, 64-2) * 4

                # Assert that it always branches
                comb += Assert(nia_o.ok == 1)

                # Check absolute or relative branching
                with m.If(AA):
                    comb += Assert(nia_o.data == imm)
                with m.Else():
                    comb += Assert(nia_o.data == (cia + imm)[0:64])

                # Make sure linking works
                with m.If(rec.lk):
                    comb += Assert(lr_o.data == (cia + 4)[0:64])
                    comb += Assert(lr_o.ok == 1)
                with m.Else():
                    comb += Assert(lr_o.ok == 0)

                # Assert that ctr is not written to
                comb += Assert(dut.o.ctr.ok == 0)

            ####
            # bc - v3.0B p37-38
            ####
            with m.Case(MicrOp.OP_BC):
                # Assert that branches are conditional
                comb += Assert(nia_o.ok == (cond_ok & ctr_ok))

                # extract target address
                BD = b_fields.BD[0:-1]
                imm = exts(BD, BD.shape().width, 64-2) * 4

                # Check absolute or relative branching
                with m.If(nia_o.ok):
                    with m.If(AA):
                        comb += Assert(nia_o.data == imm)
                    with m.Else():
                        comb += Assert(nia_o.data == (cia + imm)[0:64])
                    comb += Assert(lr_o.ok == rec.lk)
                    with m.If(rec.lk):
                        comb += Assert(lr_o.data == (cia + 4)[0:64])

                # Check that CTR is decremented
                with m.If(~BO[2]):
                    comb += Assert(dut.o.ctr.data == ctr_next)
                    comb += Assert(dut.o.ctr.ok == 1)
                with m.Else():
                    comb += Assert(dut.o.ctr.ok == 0)

            ##################
            # bctar/bcctr/bclr - v3.0B p38-39
            ##################
            with m.Case(MicrOp.OP_BCREG):
                # assert that the condition is good
                comb += Assert(nia_o.ok == (cond_ok & ctr_ok))

                with m.If(nia_o.ok):
                    # make sure we branch to the spr input
                    with m.If(xo[9] & ~xo[5]):
                        fastext = Cat(Const(0, 2), fast1[2:])
                        comb += Assert(nia_o.data == fastext[0:64])
                    with m.Else():
                        fastext = Cat(Const(0, 2), fast2[2:])
                        comb += Assert(nia_o.data == fastext[0:64])

                    # make sure branch+link works
                    comb += Assert(lr_o.ok == rec.lk)
                    with m.If(rec.lk):
                        comb += Assert(lr_o.data == (cia + 4)[0:64])

                # Check that CTR is decremented
                with m.If(~BO[2]):
                    comb += Assert(dut.o.ctr.data == ctr_next)
                    comb += Assert(dut.o.ctr.ok == 1)
                with m.Else():
                    comb += Assert(dut.o.ctr.ok == 0)
        return m


class LogicalTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=2)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
