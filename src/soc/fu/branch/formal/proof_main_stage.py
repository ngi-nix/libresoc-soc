# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, Array)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmutil.extend import exts
from nmigen.cli import rtlil

from soc.fu.branch.main_stage import BranchMainStage
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
        m.submodules.dut = dut = BranchMainStage(pspec)

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        # Full width CR register. Will have bitfield extracted for
        # feeding to branch unit
        cr = Signal(32)
        comb += cr.eq(AnyConst(32))
        cr_arr = Array([cr[(7-i)*4:(7-i)*4+4] for i in range(8)])
        cr_bit_arr = Array([cr[31-i] for i in range(32)])

        cia, cr_in, spr1, ctr = dut.i.cia, dut.i.cr, dut.i.spr1, dut.i.spr2
        lr_o, nia_o = dut.o.lr, dut.o.nia

        comb += [spr1.eq(AnyConst(64)),
                 ctr.eq(AnyConst(64)),
                 cia.eq(AnyConst(64))]

        i_fields = dut.fields.FormI
        b_fields = dut.fields.FormB
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

        # Check CR according to BO
        comb += cond_ok.eq(bo[4] | (cr_bit_arr[BI] == bo[3]))

        # CTR decrement
        ctr_next = Signal.like(ctr)
        with m.If(~BO[2]):
            comb += ctr_next.eq(ctr - 1)
        with m.Else():
            comb += ctr_next.eq(ctr)

        # CTR combpare with 0
        ctr_ok = Signal()
        comb += ctr_ok.eq(BO[2] | ((ctr != 0) ^ BO[1]))

        # Sorry, not bothering with 32 bit right now
        comb += Assume(~rec.is_32bit)

        with m.Switch(rec.insn_type):
            with m.Case(InternalOp.OP_B):
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

            with m.Case(InternalOp.OP_BC):
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
            with m.Case(InternalOp.OP_BCREG):
                # assert that the condition is good
                comb += Assert(nia_o.ok == (cond_ok & ctr_ok))

                with m.If(nia_o.ok):
                    # make sure we branch to the spr input
                    comb += Assert(nia_o.data == spr1)

                    # make sure branch+link works
                    comb += Assert(lr_o.ok == rec.lk)
                    with m.If(rec.lk):
                        comb += Assert(lr_o.data == (cia + 4)[0:64])

                # Check that CTR is decremented
                with m.If(~BO[2]):
                    comb += Assert(dut.o.ctr.data == ctr_next)
                comb += Assert(dut.o.ctr.ok != BO[2])


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
