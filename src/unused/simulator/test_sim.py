from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.simulator.internalop_sim import InternalOpSimulator
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, InternalOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form, SPR,
                                     get_signal_name, get_csv)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.simulator.qemu import run_program


class Register:
    def __init__(self, num):
        self.num = num


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, generator, simulator):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)
        gen = generator.generate_instructions()

        def process():
            for ins in gen:

                print("0x{:X}".format(ins & 0xffffffff))

                # ask the decoder to decode this binary data (endian'd)
                yield pdecode2.dec.bigendian.eq(0)  # little / big?
                yield instruction.eq(ins)          # raw binary instr.
                yield Delay(1e-6)
                yield from simulator.execute_op(pdecode2)

        sim.add_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=pdecode2.ports()):
            sim.run()

    def test_example(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "add  3, 1, 2",
               "and  4, 1, 2"]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3, 4])

    def test_ldst(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "stw  1, 0(2)",
               "lwz  3, 0(2)"]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3])

    def test_ldst_extended(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "addi 4, 0, 0x40",
               "stw  1, 0x40(2)",
               "lwzx  3, 4, 2"]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3])

    def test_ldst_widths(self):
        lst = [" lis 1, 0xdead",
               "ori 1, 1, 0xbeef",
               "addi 2, 0, 0x1000",
               "std 1, 0(2)",
               "lbz 1, 5(2)",
               "lhz 3, 4(2)",
               "lwz 4, 4(2)",
               "addi 5, 0, 0x12",
               "stb 5, 5(2)",
               "ld  5, 0(2)"]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3, 4, 5])

    def test_sub(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "subf 3, 1, 2",
               "subfic 4, 1, 0x1337",
               "neg 5, 1"]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3, 4, 5])

    def test_add_with_carry(self):
        lst = ["addi 1, 0, 5",
               "neg 1, 1",
               "addi 2, 0, 7",
               "neg 2, 2",
               "addc 3, 2, 1",
               "addi 3, 3, 1"
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3])

    def test_addis(self):
        lst = ["addi 1, 0, 0x0FFF",
               "addis 1, 1, 0x0F"
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1])

    def test_mulli(self):
        lst = ["addi 1, 0, 3",
               "mulli 1, 1, 2"
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1])

    def run_tst_program(self, prog, reglist):
        simulator = InternalOpSimulator()
        self.run_tst(prog, simulator)
        prog.reset()
        with run_program(prog) as q:
            qemu_register_compare(simulator, q, reglist)


def qemu_register_compare(simulator, qemu, regs):
    for reg in regs:
        qemu_val = qemu.get_register(reg)
        simulator.regfile.assert_gpr(reg, qemu_val)


if __name__ == "__main__":
    unittest.main()
