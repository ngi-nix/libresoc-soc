from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import sys
import os
import unittest
sys.path.append("../")
from power_decoder import (PowerDecoder)
from power_enums import (Function, InternalOp, In1Sel, In2Sel, In3Sel,
                         OutSel, RC, LdstLen, CryIn, single_bit_flags,
                         get_signal_name)


class DecoderTestCase(FHDLTestCase):
    def run_test(self, width, csvname):
        m = Module()
        comb = m.d.comb
        opcode = Signal(width)
        function_unit = Signal(Function)
        internal_op = Signal(InternalOp)
        in1_sel = Signal(In1Sel)
        in2_sel = Signal(In2Sel)
        in3_sel = Signal(In3Sel)
        out_sel = Signal(OutSel)
        rc_sel = Signal(RC)
        ldst_len = Signal(LdstLen)
        cry_in = Signal(CryIn)

        m.submodules.dut = dut = PowerDecoder(width, csvname)
        comb += [dut.opcode_in.eq(opcode),
                 function_unit.eq(dut.function_unit),
                 in1_sel.eq(dut.in1_sel),
                 in2_sel.eq(dut.in2_sel),
                 in3_sel.eq(dut.in3_sel),
                 out_sel.eq(dut.out_sel),
                 rc_sel.eq(dut.rc_sel),
                 ldst_len.eq(dut.ldst_len),
                 cry_in.eq(dut.cry_in),
                 internal_op.eq(dut.internal_op)]

        sim = Simulator(m)

        def process():
            for row in dut.opcodes:
                if not row['unit']:
                    continue
                yield opcode.eq(int(row['opcode'], 0))
                yield Delay(1e-6)
                signals = [(function_unit, Function, 'unit'),
                           (internal_op, InternalOp, 'internal op'),
                           (in1_sel, In1Sel, 'in1'),
                           (in2_sel, In2Sel, 'in2'),
                           (in3_sel, In3Sel, 'in3'),
                           (out_sel, OutSel, 'out'),
                           (rc_sel, RC, 'rc'),
                           (cry_in, CryIn, 'cry in'),
                           (ldst_len, LdstLen, 'ldst len')]
                for sig, enm, name in signals:
                    result = yield sig
                    expected = enm[row[name]]
                    msg = f"{sig.name} == {enm(result)}, expected: {expected}"
                    self.assertEqual(enm(result), expected, msg)
                for bit in single_bit_flags:
                    sig = getattr(dut, get_signal_name(bit))
                    result = yield sig
                    expected = int(row[bit])
                    msg = f"{sig.name} == {result}, expected: {expected}"
                    self.assertEqual(expected, result, msg)
        sim.add_process(process)
        with sim.write_vcd("test.vcd", "test.gtkw", traces=[
                opcode, function_unit, internal_op,
                in1_sel, in2_sel]):
            sim.run()

    def generate_ilang(self, width, csvname):
        prefix = os.path.splitext(csvname)[0]
        dut = PowerDecoder(width, csvname)
        vl = rtlil.convert(dut, ports=dut.ports())
        with open("%s_decoder.il" % prefix, "w") as f:
            f.write(vl)

    def test_major(self):
        self.run_test(6, "major.csv")
        self.generate_ilang(6, "major.csv")

    def test_minor_19(self):
        self.run_test(3, "minor_19.csv")
        self.generate_ilang(3, "minor_19.csv")

    def test_minor_30(self):
        self.run_test(4, "minor_30.csv")
        self.generate_ilang(4, "minor_30.csv")

    def test_minor_31(self):
        self.run_test(10, "minor_31.csv")
        self.generate_ilang(10, "minor_31.csv")

if __name__ == "__main__":
    unittest.main()
