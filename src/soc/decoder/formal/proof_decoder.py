from nmigen import Module, Signal, Elaboratable, Cat
from nmigen.asserts import Assert, AnyConst, Assume
from nmutil.formaltest import FHDLTestCase

from openpower.decoder.power_decoder import create_pdecode, PowerOp
from openpower.decoder.power_enums import (In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, Form, Function,
                                     LdstLen, CryIn,
                                     MicrOp, SPR, get_csv)
from openpower.decoder.power_decoder2 import (PowerDecode2,
                                        Decode2ToExecute1Type)
import unittest
import pdb

class Driver(Elaboratable):
    def __init__(self):
        self.instruction = Signal(32, reset_less=True)
        self.m = None
        self.comb = None

    def elaborate(self, platform):
        self.m = Module()
        self.comb = self.m.d.comb
        self.instruction = Signal(32)

        self.comb += self.instruction.eq(AnyConst(32))

        pdecode = create_pdecode()

        self.m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        dec1 = pdecode2.dec
        self.comb += pdecode2.dec.bigendian.eq(1) # TODO: bigendian=0
        self.comb += pdecode2.dec.raw_opcode_in.eq(self.instruction)

        # ignore special decoding of nop
        self.comb += Assume(self.instruction != 0x60000000)

        #self.assert_dec1_decode(dec1, dec1.dec)

        self.assert_form(dec1, pdecode2)
        return self.m

    def assert_dec1_decode(self, dec1, decoders):
        if not isinstance(decoders, list):
            decoders = [decoders]
        for d in decoders:
            print(d.pattern)
            opcode_switch = Signal(d.bitsel[1] - d.bitsel[0])
            self.comb += opcode_switch.eq(
                self.instruction[d.bitsel[0]:d.bitsel[1]])
            with self.m.Switch(opcode_switch):
                self.handle_subdecoders(dec1, d)
                for row in d.opcodes:
                    opcode = row['opcode']
                    if d.opint and '-' not in opcode:
                        opcode = int(opcode, 0)
                    if not row['unit']:
                        continue
                    with self.m.Case(opcode):
                        self.comb += self.assert_dec1_signals(dec1, row)
                with self.m.Default():
                    self.comb += Assert(dec.op.internal_op ==
                                        MicrOp.OP_ILLEGAL)
                                        

    def handle_subdecoders(self, dec1, decoders):
        for dec in decoders.subdecoders:
            if isinstance(dec, list):
                pattern = dec[0].pattern
            else:
                pattern = dec.pattern
            with self.m.Case(pattern):
                self.assert_dec1_decode(dec1, dec)

    def assert_dec1_signals(self, dec, row):
        op = dec.op
        return [Assert(op.function_unit == Function[row['unit']]),
                Assert(op.internal_op == MicrOp[row['internal op']]),
                Assert(op.in1_sel == In1Sel[row['in1']]),
                Assert(op.in2_sel == In2Sel[row['in2']]),
                Assert(op.in3_sel == In3Sel[row['in3']]),
                Assert(op.out_sel == OutSel[row['out']]),
                Assert(op.ldst_len == LdstLen[row['ldst len']]),
                Assert(op.rc_sel == RC[row['rc']]),
                Assert(op.cry_in == CryIn[row['cry in']]),
                Assert(op.form == Form[row['form']]),
                ]

    # This is to assert that the decoder conforms to the table listed
    # in PowerISA public spec v3.0B, Section 1.6, page 12
    def assert_form(self, dec, dec2):
        with self.m.Switch(dec.op.form):
            with self.m.Case(Form.A):
                self.comb += Assert(dec.op.in1_sel.matches(
                    In1Sel.NONE, In1Sel.RA, In1Sel.RA_OR_ZERO))
                self.comb += Assert(dec.op.in2_sel.matches(
                    In2Sel.RB, In2Sel.NONE))
                self.comb += Assert(dec.op.in3_sel.matches(
                    In3Sel.RS, In3Sel.NONE))
                self.comb += Assert(dec.op.out_sel.matches(
                    OutSel.NONE, OutSel.RT))
                # The table has fields for XO and Rc, but idk what they correspond to
            with self.m.Case(Form.B):
                pass
            with self.m.Case(Form.D):
                self.comb += Assert(dec.op.in1_sel.matches(
                    In1Sel.NONE, In1Sel.RA, In1Sel.RA_OR_ZERO))
                self.comb += Assert(dec.op.in2_sel.matches(
                    In2Sel.CONST_UI, In2Sel.CONST_SI, In2Sel.CONST_UI_HI,
                    In2Sel.CONST_SI_HI))
                self.comb += Assert(dec.op.out_sel.matches(
                    OutSel.NONE, OutSel.RT, OutSel.RA))
            with self.m.Case(Form.I):
                self.comb += Assert(dec.op.in2_sel.matches(
                    In2Sel.CONST_LI))

    def instr_bits(self, start, end=None):
        if not end:
            end = start
        return self.instruction[::-1][start:end+1]

class DecoderTestCase(FHDLTestCase):
    def test_decoder(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)

if __name__ == '__main__':
    unittest.main()
