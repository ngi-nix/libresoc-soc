# Proof of correctness for SPR pipeline, main stage


"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=418
"""

import unittest

from nmigen import (Elaboratable, Module, Signal, Cat)
from nmigen.asserts import Assert, AnyConst, Assume
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase

from soc.fu.spr.main_stage import SPRMainStage
from soc.fu.spr.pipe_data import SPRPipeSpec
from soc.fu.spr.spr_input_record import CompSPROpSubset

from openpower.decoder.power_decoder2 import decode_spr_num
from openpower.decoder.power_enums import MicrOp, SPR, XER_bits
from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange

# use POWER numbering. sigh.
def xer_bit(name):
    return 63-XER_bits[name]


class Driver(Elaboratable):
    """
    Defines a module to drive the device under test and assert properties
    about its outputs.
    """

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # cookie-cutting most of this from alu formal proof_main_stage.py

        rec = CompSPROpSubset()
        # Setup random inputs for dut.op
        for p in rec.ports():
            width = p.width
            comb += p.eq(AnyConst(width))

        pspec = SPRPipeSpec(id_wid=2)
        m.submodules.dut = dut = SPRMainStage(pspec)

        # frequently used aliases
        a = dut.i.a
        ca_in = dut.i.xer_ca[0]   # CA carry in
        ca32_in = dut.i.xer_ca[1] # CA32 carry in 32
        so_in = dut.i.xer_so      # SO sticky overflow
        ov_in = dut.i.xer_ov[0]   # XER OV in
        ov32_in = dut.i.xer_ov[1] # XER OV32 in
        o = dut.o.o

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 ca_in.eq(AnyConst(0b11)),
                 so_in.eq(AnyConst(1))]

        # and for the context muxid
        width = dut.i.ctx.muxid.width
        comb += dut.i.ctx.muxid.eq(AnyConst(width))

        # assign the PowerDecode2 operation subset
        comb += dut.i.ctx.op.eq(rec)

        # check that the operation (op) is passed through (and muxid)
        comb += Assert(dut.o.ctx.op == dut.i.ctx.op )
        comb += Assert(dut.o.ctx.muxid == dut.i.ctx.muxid )

        # MTSPR
        fields = DecodeFields(SignalBitRange, [dut.i.ctx.op.insn])
        fields.create_specs()
        xfx = fields.FormXFX
        spr = Signal(len(xfx.SPR))
        comb += spr.eq(decode_spr_num(xfx.SPR))

        with m.Switch(dut.i.ctx.op.insn_type):

            # OP_MTSPR
            with m.Case(MicrOp.OP_MTSPR):
                with m.Switch(spr):
                    with m.Case(SPR.CTR, SPR.LR, SPR.TAR, SPR.SRR0, SPR.SRR1):
                        comb += [
                            Assert(dut.o.fast1.data == a),
                            Assert(dut.o.fast1.ok),

                            # If a fast-path SPR is referenced, no other OKs
                            # can fire.
                            Assert(~dut.o.xer_so.ok),
                            Assert(~dut.o.xer_ov.ok),
                            Assert(~dut.o.xer_ca.ok),
                        ]
                    with m.Case(SPR.XER):
                        comb += [
                            Assert(dut.o.xer_so.data == a[xer_bit('SO')]),
                            Assert(dut.o.xer_so.ok),
                            Assert(dut.o.xer_ov.data == Cat(
                                a[xer_bit('OV')], a[xer_bit('OV32')]
                            )),
                            Assert(dut.o.xer_ov.ok),
                            Assert(dut.o.xer_ca.data == Cat(
                                a[xer_bit('CA')], a[xer_bit('CA32')]
                            )),
                            Assert(dut.o.xer_ca.ok),

                            # XER is not a fast-path SPR.
                            Assert(~dut.o.fast1.ok),
                        ]
                    # slow SPRs TODO

            # OP_MFSPR
            with m.Case(MicrOp.OP_MFSPR):
                comb += Assert(o.ok)
                with m.Switch(spr):
                    with m.Case(SPR.CTR, SPR.LR, SPR.TAR, SPR.SRR0, SPR.SRR1):
                        comb += Assert(o.data == dut.i.fast1)
                    with m.Case(SPR.XER):
                        bits = {
                            'SO': so_in,
                            'OV': ov_in,
                            'OV32': ov32_in,
                            'CA': ca_in,
                            'CA32': ca32_in,
                        }
                        comb += [
                            Assert(o[xer_bit(b)] == bits[b])
                            for b in bits
                        ]
                    # slow SPRs TODO

        return m


class SPRMainStageTestCase(FHDLTestCase):
    def test_formal(self):
        self.assertFormal(Driver(), mode="bmc", depth=100)
        self.assertFormal(Driver(), mode="cover", depth=100)

    def test_ilang(self):
        vl = rtlil.convert(Driver(), ports=[])
        with open("spr_main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
