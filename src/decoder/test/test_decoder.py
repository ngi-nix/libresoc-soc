from nmigen import Module, Elaboratable, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import sys
import unittest
sys.path.append("../")
from decoder import PowerDecoder, Function, major_opcodes

class DecoderTestCase(FHDLTestCase):
    def test_function_unit(self):
        m = Module()
        comb = m.d.comb
        opcode = Signal(6)
        function_unit = Signal(Function)

        m.submodules.dut = dut = PowerDecoder()
        comb += [dut.opcode_in.eq(opcode),
                 function_unit.eq(dut.function_unit)]

        sim = Simulator(m)
        def process():
            for row in major_opcodes:
                yield opcode.eq(int(row['opcode']))
                yield Delay(1e-6)
                result = yield function_unit
                expected = Function[row['unit']].value
                self.assertEqual(expected, result)
        sim.add_process(process)
        with sim.write_vcd("test.vcd", "test.gtkw", traces=[opcode, function_unit]):
            sim.run()

    def test_ilang(self):
        dut = PowerDecoder()
        vl = rtlil.convert(dut, ports=[dut.opcode_in, dut.function_unit])
        with open("power_decoder.il", "w") as f:
            f.write(vl)

if __name__ == "__main__":
    unittest.main()

