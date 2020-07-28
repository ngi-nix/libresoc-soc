# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=340
"""

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil

from soc.fu.shift_rot.main_stage import ShiftRotMainStage
from soc.fu.shift_rot.rotator import right_mask, left_mask
from soc.fu.shift_rot.pipe_data import ShiftRotPipeSpec
from soc.fu.shift_rot.sr_input_record import CompSROpSubset
from soc.decoder.power_enums import MicrOp
import unittest
from nmutil.extend import exts


# This defines a module to drive the device under test and assert
# properties about its outputs
class Driver(Elaboratable):
    def __init__(self):
        # inputs and outputs
        pass

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        rec = CompSROpSubset()
        # Setup random inputs for dut.op
        for p in rec.ports():
            comb += p.eq(AnyConst(p.width))

        pspec = ShiftRotPipeSpec(id_wid=2)
        m.submodules.dut = dut = ShiftRotMainStage(pspec)

        # convenience variables
        a = dut.i.rs
        b = dut.i.rb
        ra = dut.i.a
        carry_in = dut.i.xer_ca[0]
        carry_in32 = dut.i.xer_ca[1]
        carry_out = dut.o.xer_ca
        o = dut.o.o.data
        print ("fields", rec.fields)
        itype = rec.insn_type

        # instruction fields
        m_fields = dut.fields.FormM
        md_fields = dut.fields.FormMD

        # setup random inputs
        comb += a.eq(AnyConst(64))
        comb += b.eq(AnyConst(64))
        comb += carry_in.eq(AnyConst(1))
        comb += carry_in32.eq(AnyConst(1))

        # copy operation
        comb += dut.i.ctx.op.eq(rec)

        # check that the operation (op) is passed through (and muxid)
        comb += Assert(dut.o.ctx.op == dut.i.ctx.op)
        comb += Assert(dut.o.ctx.muxid == dut.i.ctx.muxid)

        # signed and signed/32 versions of input a
        a_signed = Signal(signed(64))
        a_signed_32 = Signal(signed(32))
        comb += a_signed.eq(a)
        comb += a_signed_32.eq(a[0:32])

        # masks: start-left
        mb = Signal(7, reset_less=True)
        ml = Signal(64, reset_less=True)

        # clear left?
        with m.If((itype == MicrOp.OP_RLC) | (itype == MicrOp.OP_RLCL)):
            with m.If(rec.is_32bit):
                comb += mb.eq(m_fields.MB[0:-1])
            with m.Else():
                comb += mb.eq(md_fields.mb[0:-1])
        with m.Else():
            with m.If(rec.is_32bit):
                comb += mb.eq(b[0:6])
            with m.Else():
                comb += mb.eq(b+32)
        comb += ml.eq(left_mask(m, mb))

        # masks: end-right
        me = Signal(7, reset_less=True)
        mr = Signal(64, reset_less=True)

        # clear right?
        with m.If((itype == MicrOp.OP_RLC) | (itype == MicrOp.OP_RLCR)):
            with m.If(rec.is_32bit):
                comb += me.eq(m_fields.ME[0:-1])
            with m.Else():
                comb += me.eq(md_fields.me[0:-1])
        with m.Else():
            with m.If(rec.is_32bit):
                comb += me.eq(b[0:6])
            with m.Else():
                comb += me.eq(63-b)
        comb += mr.eq(right_mask(m, me))

        # must check Data.ok
        o_ok = Signal()
        comb += o_ok.eq(1)

        # main assertion of arithmetic operations
        with m.Switch(itype):

            # left-shift: 64/32-bit
            with m.Case(MicrOp.OP_SHL):
                comb += Assume(ra == 0)
                with m.If(rec.is_32bit):
                    comb += Assert(o[0:32] == ((a << b[0:6]) & 0xffffffff))
                    comb += Assert(o[32:64] == 0)
                with m.Else():
                    comb += Assert(o == ((a << b[0:7]) & ((1 << 64)-1)))

            # right-shift: 64/32-bit / signed
            with m.Case(MicrOp.OP_SHR):
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

            # extswsli: 32/64-bit moded
            with m.Case(MicrOp.OP_EXTSWSLI):
                comb += Assume(ra == 0)
                with m.If(rec.is_32bit):
                    comb += Assert(o[0:32] == ((a << b[0:6]) & 0xffffffff))
                    comb += Assert(o[32:64] == 0)
                with m.Else():
                    # sign-extend to 64 bit
                    a_s = Signal(64, reset_less=True)
                    comb += a_s.eq(exts(a, 32, 64))
                    comb += Assert(o == ((a_s << b[0:7]) & ((1 << 64)-1)))

            #TODO
            with m.Case(MicrOp.OP_RLC):
                pass
            with m.Case(MicrOp.OP_RLCR):
                pass
            with m.Case(MicrOp.OP_RLCL):
                pass
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
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
