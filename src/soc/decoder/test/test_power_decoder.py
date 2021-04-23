from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Delay

from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import os
import unittest
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_enums import (Function, MicrOp,
                                     In1Sel, In2Sel, In3Sel,
                                     CRInSel, CROutSel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags,
                                     get_signal_name, get_csv)


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, bitsel, csvname, minor=None, suffix=None, opint=True):
        m = Module()
        comb = m.d.comb
        opcode = Signal(32)
        function_unit = Signal(Function)
        internal_op = Signal(MicrOp)
        in1_sel = Signal(In1Sel)
        in2_sel = Signal(In2Sel)
        in3_sel = Signal(In3Sel)
        out_sel = Signal(OutSel)
        cr_in = Signal(CRInSel)
        cr_out = Signal(CROutSel)
        rc_sel = Signal(RC)
        ldst_len = Signal(LdstLen)
        cry_in = Signal(CryIn)
        bigendian = Signal()
        comb += bigendian.eq(1)

        # opcodes = get_csv(csvname)
        m.submodules.dut = dut = create_pdecode()
        comb += [dut.raw_opcode_in.eq(opcode),
                 dut.bigendian.eq(bigendian),
                 function_unit.eq(dut.op.function_unit),
                 in1_sel.eq(dut.op.in1_sel),
                 in2_sel.eq(dut.op.in2_sel),
                 in3_sel.eq(dut.op.in3_sel),
                 out_sel.eq(dut.op.out_sel),
                 cr_in.eq(dut.op.cr_in),
                 cr_out.eq(dut.op.cr_out),
                 rc_sel.eq(dut.op.rc_sel),
                 ldst_len.eq(dut.op.ldst_len),
                 cry_in.eq(dut.op.cry_in),
                 internal_op.eq(dut.op.internal_op)]

        sim = Simulator(m)
        opcodes = get_csv(csvname)

        def process():
            for row in opcodes:
                if not row['unit']:
                    continue
                op = row['opcode']
                if not opint:  # HACK: convert 001---10 to 0b00100010
                    op = "0b" + op.replace('-', '0')
                print("opint", opint, row['opcode'], op)
                print(row)
                yield opcode.eq(0)
                yield opcode[bitsel[0]:bitsel[1]].eq(int(op, 0))
                if minor:
                    print(minor)
                    minorbits = minor[1]
                    yield opcode[minorbits[0]:minorbits[1]].eq(minor[0])
                else:
                    # OR 0, 0, 0  ; 0x60000000 is decoded as a NOP
                    # If we're testing the OR instruction, make sure
                    # that the instruction is not 0x60000000
                    if int(op, 0) == 24:
                        yield opcode[24:25].eq(0b11)

                yield Delay(1e-6)
                signals = [(function_unit, Function, 'unit'),
                           (internal_op, MicrOp, 'internal op'),
                           (in1_sel, In1Sel, 'in1'),
                           (in2_sel, In2Sel, 'in2'),
                           (in3_sel, In3Sel, 'in3'),
                           (out_sel, OutSel, 'out'),
                           (cr_in, CRInSel, 'CR in'),
                           (cr_out, CROutSel, 'CR out'),
                           (rc_sel, RC, 'rc'),
                           (cry_in, CryIn, 'cry in'),
                           (ldst_len, LdstLen, 'ldst len')]
                for sig, enm, name in signals:
                    result = yield sig
                    expected = enm[row[name]]
                    msg = f"{sig.name} == {enm(result)}, expected: {expected}"
                    self.assertEqual(enm(result), expected, msg)
                for bit in single_bit_flags:
                    sig = getattr(dut.op, get_signal_name(bit))
                    result = yield sig
                    expected = int(row[bit])
                    msg = f"{sig.name} == {result}, expected: {expected}"
                    self.assertEqual(expected, result, msg)
        sim.add_process(process)
        prefix = os.path.splitext(csvname)[0]
        with sim.write_vcd("%s.vcd" % prefix, "%s.gtkw" % prefix, traces=[
                opcode, function_unit, internal_op,
                in1_sel, in2_sel]):
            sim.run()

    def generate_ilang(self):
        pdecode = create_pdecode()
        vl = rtlil.convert(pdecode, ports=pdecode.ports())
        with open("decoder.il", "w") as f:
            f.write(vl)

    def test_major(self):
        self.run_tst((26, 32), "major.csv")
        self.generate_ilang()

    def test_minor_19(self):
        self.run_tst((1, 11), "minor_19.csv", minor=(19, (26, 32)),
                     suffix=(0, 5))

    # def test_minor_19_00000(self):
    #     self.run_tst((1, 11), "minor_19_00000.csv")

    def test_minor_30(self):
        self.run_tst((1, 5), "minor_30.csv", minor=(30, (26, 32)))

    def test_minor_31(self):
        self.run_tst((1, 11), "minor_31.csv", minor=(31, (26, 32)))

    def test_minor_58(self):
        self.run_tst((0, 2), "minor_58.csv", minor=(58, (26, 32)))

    def test_minor_62(self):
        self.run_tst((0, 2), "minor_62.csv", minor=(62, (26, 32)))

    # #def test_minor_31_prefix(self):
    # #    self.run_tst(10, "minor_31.csv", suffix=(5, 10))

    # def test_extra(self):
    #     self.run_tst(32, "extra.csv", opint=False)
    #     self.generate_ilang(32, "extra.csv", opint=False)


if __name__ == "__main__":
    unittest.main()
