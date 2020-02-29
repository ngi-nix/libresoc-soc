from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import sys
import unittest
sys.path.append("../")
from power_major_decoder import (PowerMajorDecoder, Function,
                                 In1Sel, In2Sel, In3Sel, OutSel,
                                 single_bit_flags, get_signal_name,
                                 InternalOp, major_opcodes)


class DecoderTestCase(FHDLTestCase):
    def test_function_unit(self):
        m = Module()
        comb = m.d.comb
        opcode = Signal(6)
        function_unit = Signal(Function)
        internal_op = Signal(InternalOp)
        in1_sel = Signal(In1Sel)
        in2_sel = Signal(In2Sel)
        in3_sel = Signal(In3Sel)
        out_sel = Signal(OutSel)

        m.submodules.dut = dut = PowerMajorDecoder()
        comb += [dut.opcode_in.eq(opcode),
                 function_unit.eq(dut.function_unit),
                 in1_sel.eq(dut.in1_sel),
                 in2_sel.eq(dut.in2_sel),
                 in3_sel.eq(dut.in3_sel),
                 out_sel.eq(dut.out_sel),
                 internal_op.eq(dut.internal_op)]

        sim = Simulator(m)

        def process():
            for row in major_opcodes:
                yield opcode.eq(int(row['opcode']))
                yield Delay(1e-6)
                result = yield function_unit
                expected = Function[row['unit']].value
                self.assertEqual(expected, result)

                result = yield internal_op
                expected = InternalOp[row['internal op']].value
                self.assertEqual(expected, result)

                result = yield in1_sel
                expected = In1Sel[row['in1']].value
                self.assertEqual(expected, result)

                result = yield in2_sel
                expected = In2Sel[row['in2']].value
                self.assertEqual(expected, result)

                result = yield in3_sel
                expected = In3Sel[row['in3']].value
                self.assertEqual(expected, result)

                result = yield out_sel
                expected = OutSel[row['out']].value
                self.assertEqual(expected, result)

                for bit in single_bit_flags:
                    sig = getattr(dut, get_signal_name(bit))
                    result = yield sig
                    expected = int(row[bit])
                    self.assertEqual(expected, result)
        sim.add_process(process)
        with sim.write_vcd("test.vcd", "test.gtkw", traces=[
                opcode, function_unit, internal_op,
                in1_sel, in2_sel]):
            sim.run()

    def test_ilang(self):
        dut = PowerMajorDecoder()
        vl = rtlil.convert(dut, ports=dut.ports())
        with open("power_major_decoder.il", "w") as f:
            f.write(vl)


if __name__ == "__main__":
    unittest.main()
