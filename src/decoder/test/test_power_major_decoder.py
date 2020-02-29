from nmigen import Module, Elaboratable, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import sys
import unittest
sys.path.append("../")
from power_major_decoder import (PowerMajorDecoder, Function,
                                InternalOp, major_opcodes)

class DecoderTestCase(FHDLTestCase):
    def test_function_unit(self):
        m = Module()
        comb = m.d.comb
        opcode = Signal(6)
        function_unit = Signal(Function)
        internal_op = Signal(InternalOp)

        m.submodules.dut = dut = PowerMajorDecoder()
        comb += [dut.opcode_in.eq(opcode),
                 function_unit.eq(dut.function_unit),
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
        sim.add_process(process)
        with sim.write_vcd("test.vcd", "test.gtkw", traces=[opcode, function_unit, internal_op]):
            sim.run()

    def test_ilang(self):
        dut = PowerMajorDecoder()
        vl = rtlil.convert(dut, ports=[dut.opcode_in, dut.function_unit])
        with open("power_major_decoder.il", "w") as f:
            f.write(vl)

if __name__ == "__main__":
    unittest.main()

