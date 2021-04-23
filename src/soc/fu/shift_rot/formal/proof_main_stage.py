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
from openpower.decoder.power_enums import MicrOp
from openpower.consts import field

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
        # Setup random inputs for dut.op.  do them explicitly so that
        # we can see which ones cause failures in the debug report
        #for p in rec.ports():
        #    comb += p.eq(AnyConst(p.width))
        comb += rec.insn_type.eq(AnyConst(rec.insn_type.width))
        comb += rec.fn_unit.eq(AnyConst(rec.fn_unit.width))
        comb += rec.imm_data.imm.eq(AnyConst(rec.imm_data.imm.width))
        comb += rec.imm_data.imm_ok.eq(AnyConst(rec.imm_data.imm_ok.width))
        comb += rec.rc.rc.eq(AnyConst(rec.rc.rc.width))
        comb += rec.rc.rc_ok.eq(AnyConst(rec.rc.rc_ok.width))
        comb += rec.oe.oe.eq(AnyConst(rec.oe.oe.width))
        comb += rec.oe.oe_ok.eq(AnyConst(rec.oe.oe_ok.width))
        comb += rec.write_cr0.eq(AnyConst(rec.write_cr0.width))
        comb += rec.input_carry.eq(AnyConst(rec.input_carry.width))
        comb += rec.output_carry.eq(AnyConst(rec.output_carry.width))
        comb += rec.input_cr.eq(AnyConst(rec.input_cr.width))
        comb += rec.is_32bit.eq(AnyConst(rec.is_32bit.width))
        comb += rec.is_signed.eq(AnyConst(rec.is_signed.width))
        comb += rec.insn.eq(AnyConst(rec.insn.width))


        pspec = ShiftRotPipeSpec(id_wid=2)
        m.submodules.dut = dut = ShiftRotMainStage(pspec)

        # convenience variables
        rs = dut.i.rs  # register to shift
        b = dut.i.rb   # register containing amount to shift by
        ra = dut.i.a   # source register if masking is to be done
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
        comb += rs.eq(AnyConst(64))
        comb += ra.eq(AnyConst(64))
        comb += b.eq(AnyConst(64))
        comb += carry_in.eq(AnyConst(1))
        comb += carry_in32.eq(AnyConst(1))

        # copy operation
        comb += dut.i.ctx.op.eq(rec)

        # check that the operation (op) is passed through (and muxid)
        comb += Assert(dut.o.ctx.op == dut.i.ctx.op)
        comb += Assert(dut.o.ctx.muxid == dut.i.ctx.muxid)

        # signed and signed/32 versions of input rs
        a_signed = Signal(signed(64))
        a_signed_32 = Signal(signed(32))
        comb += a_signed.eq(rs)
        comb += a_signed_32.eq(rs[0:32])

        # masks: start-left
        mb = Signal(7, reset_less=True)
        ml = Signal(64, reset_less=True)

        # clear left?
        with m.If((itype == MicrOp.OP_RLC) | (itype == MicrOp.OP_RLCL)):
            with m.If(rec.is_32bit):
                comb += mb.eq(m_fields.MB)
            with m.Else():
                comb += mb.eq(md_fields.mb)
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
                comb += me.eq(m_fields.ME)
            with m.Else():
                comb += me.eq(md_fields.me)
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
                    comb += Assert(o[0:32] == ((rs << b[0:6]) & 0xffffffff))
                    comb += Assert(o[32:64] == 0)
                with m.Else():
                    comb += Assert(o == ((rs << b[0:7]) & ((1 << 64)-1)))

            # right-shift: 64/32-bit / signed
            with m.Case(MicrOp.OP_SHR):
                comb += Assume(ra == 0)
                with m.If(~rec.is_signed):
                    with m.If(rec.is_32bit):
                        comb += Assert(o[0:32] == (rs[0:32] >> b[0:6]))
                        comb += Assert(o[32:64] == 0)
                    with m.Else():
                        comb += Assert(o == (rs >> b[0:7]))
                with m.Else():
                    with m.If(rec.is_32bit):
                        comb += Assert(o[0:32] == (a_signed_32 >> b[0:6]))
                        comb += Assert(o[32:64] == Repl(rs[31], 32))
                    with m.Else():
                        comb += Assert(o == (a_signed >> b[0:7]))

            # extswsli: 32/64-bit moded
            with m.Case(MicrOp.OP_EXTSWSLI):
                comb += Assume(ra == 0)
                with m.If(rec.is_32bit):
                    comb += Assert(o[0:32] == ((rs << b[0:6]) & 0xffffffff))
                    comb += Assert(o[32:64] == 0)
                with m.Else():
                    # sign-extend to 64 bit
                    a_s = Signal(64, reset_less=True)
                    comb += a_s.eq(exts(rs, 32, 64))
                    comb += Assert(o == ((a_s << b[0:7]) & ((1 << 64)-1)))

            # rlwinm, rlwnm, rlwimi
            # *CAN* these even be 64-bit capable?  I don't think they are.
            with m.Case(MicrOp.OP_RLC):
                comb += Assume(ra == 0)
                comb += Assume(rec.is_32bit)

                # Duplicate some signals so that they're much easier to find
                # in gtkwave.
                # Pro-tip: when debugging, factor out expressions into
                # explicitly named
                # signals, and search using a unique grep-tag (RLC in my case).
                #   After
                # debugging, resubstitute values to comply with surrounding
                # code norms.

                mrl = Signal(64, reset_less=True, name='MASK_FOR_RLC')
                with m.If(mb > me):
                    comb += mrl.eq(ml | mr)
                with m.Else():
                    comb += mrl.eq(ml & mr)

                ainp = Signal(64, reset_less=True, name='A_INP_FOR_RLC')
                comb += ainp.eq(field(rs, 32, 63))

                sh = Signal(6, reset_less=True, name='SH_FOR_RLC')
                comb += sh.eq(b[0:6])

                exp_shl = Signal(64, reset_less=True,
                                    name='A_SHIFTED_LEFT_BY_SH_FOR_RLC')
                comb += exp_shl.eq((ainp << sh) & 0xFFFFFFFF)

                exp_shr = Signal(64, reset_less=True,
                                    name='A_SHIFTED_RIGHT_FOR_RLC')
                comb += exp_shr.eq((ainp >> (32 - sh)) & 0xFFFFFFFF)

                exp_rot = Signal(64, reset_less=True,
                                    name='A_ROTATED_LEFT_FOR_RLC')
                comb += exp_rot.eq(exp_shl | exp_shr)

                exp_ol = Signal(32, reset_less=True, name='EXPECTED_OL_FOR_RLC')
                comb += exp_ol.eq(field((exp_rot & mrl) | (ainp & ~mrl),
                                    32, 63))

                act_ol = Signal(32, reset_less=True, name='ACTUAL_OL_FOR_RLC')
                comb += act_ol.eq(field(o, 32, 63))

                # If I uncomment the following lines, I can confirm that all
                # 32-bit rotations work.  If I uncomment only one of the
                # following lines, I can confirm that all 32-bit rotations
                # work.  When I remove/recomment BOTH lines, however, the
                # assertion fails.  Why??

#               comb += Assume(mr == 0xFFFFFFFF)
#               comb += Assume(ml == 0xFFFFFFFF)
                #with m.If(rec.is_32bit):
                #    comb += Assert(act_ol == exp_ol)
                #    comb += Assert(field(o, 0, 31) == 0)

            #TODO
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
