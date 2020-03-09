from nmigen import Module, Signal, Elaboratable
from nmigen.asserts import Assert, AnyConst
from nmigen.test.utils import FHDLTestCase

from soc.decoder.power_decoder import create_pdecode, PowerOp
from soc.decoder.power_enums import (In1Sel, In2Sel, In3Sel,
                                     InternalOp, SPR)
from soc.decoder.power_decoder2 import (PowerDecode2,
                                        Decode2ToExecute1Type)
import unittest

class Driver(Elaboratable):
    def __init__(self):
        pass
    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        comb += instruction.eq(AnyConst(32))

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.opcode_in.eq(instruction)

        self.test_in1(m, pdecode2, pdecode)

        return m

    def test_in1(self, m, pdecode2, pdecode):
        ra = pdecode.RA[0:-1]
        with m.If(pdecode.op.in1_sel == In1Sel.RA):
            m.d.comb += Assert(pdecode2.e.read_reg1.data == ra)
            m.d.comb += Assert(pdecode2.e.read_reg1.ok == 1)
        with m.If(pdecode.op.in1_sel == In1Sel.RA_OR_ZERO):
            with m.If(ra == 0):
                m.d.comb += Assert(pdecode2.e.read_reg1.ok == 0)
            with m.Else():
                m.d.comb += Assert(pdecode2.e.read_reg1.data == ra)
                m.d.comb += Assert(pdecode2.e.read_reg1.ok == 1)
        op = pdecode.op.internal_op
        with m.If((op == InternalOp.OP_BC) |
                  (op == InternalOp.OP_BCREG)):
            with m.If(~pdecode.BO[2]):
                m.d.comb += Assert(pdecode2.e.read_spr1.data == SPR.CTR)
                m.d.comb += Assert(pdecode2.e.read_spr1.ok == 1)
        with m.If((op == InternalOp.OP_MFSPR) |
                  (op == InternalOp.OP_MTSPR)):
            m.d.comb += Assert(pdecode2.e.read_spr1.data == pdecode.SPR[0:-1])
            m.d.comb += Assert(pdecode2.e.read_spr1.ok == 1)


class Decoder2TestCase(FHDLTestCase):
    def test_decoder2(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)

if __name__ == '__main__':
    unittest.main()
