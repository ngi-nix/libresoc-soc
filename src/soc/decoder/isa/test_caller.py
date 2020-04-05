from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.decoder.isa.caller import ISACaller
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.decoder.isa.caller import ISACaller, inject
from soc.decoder.selectable_int import SelectableInt
from soc.decoder.orderedset import OrderedSet
from soc.decoder.isa import ISA


class Register:
    def __init__(self, num):
        self.num = num


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, generator, initial_regs):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()
        simulator = ISA(pdecode, initial_regs)

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)
        gen = generator.generate_instructions()

        def process():
            for ins, code in zip(gen, generator.assembly.splitlines()):

                print("0x{:X}".format(ins & 0xffffffff))
                print(code)

                # ask the decoder to decode this binary data (endian'd)
                yield pdecode2.dec.bigendian.eq(0)  # little / big?
                yield instruction.eq(ins)          # raw binary instr.
                yield Delay(1e-6)
                opname = code.split(' ')[0]
                yield from simulator.call(opname)

        sim.add_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()
        return simulator

    def test_add(self):
        lst = ["add 1, 3, 2"]
        initial_regs = [0] * 32
        initial_regs[3] = 0x1234
        initial_regs[2] = 0x4321
        with Program(lst) as program:
            sim = self.run_test_program(program, initial_regs)
            self.assertEqual(sim.gpr(1), SelectableInt(0x5555, 64))

    def test_addi(self):
        lst = ["addi 3, 0, 0x1234",
               "addi 2, 0, 0x4321",
               "add  1, 3, 2"]
        with Program(lst) as program:
            sim = self.run_test_program(program)
            print(sim.gpr(1))
            self.assertEqual(sim.gpr(1), SelectableInt(0x5555, 64))

    def test_load_store(self):
        lst = ["addi 1, 0, 0x0010",
               "addi 2, 0, 0x1234",
               "stw 2, 0(1)",
               "lwz 3, 0(1)"]
        with Program(lst) as program:
            sim = self.run_test_program(program)
            print(sim.gpr(1))
            self.assertEqual(sim.gpr(3), SelectableInt(0x1234, 64))

    def run_test_program(self, prog, initial_regs=[0] * 32):
        simulator = self.run_tst(prog, initial_regs)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
