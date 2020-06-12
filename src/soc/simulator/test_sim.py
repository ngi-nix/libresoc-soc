from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, InternalOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form, SPR,
                                     get_signal_name, get_csv)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.simulator.qemu import run_program
from soc.decoder.isa.all import ISA


class Register:
    def __init__(self, num):
        self.num = num


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, generator):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        simulator = ISA(pdecode2, [0] * 32, {}, 0, {}, 0)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        comb += pdecode2.dec.bigendian.eq(0)
        gen = generator.generate_instructions()
        instructions = list(zip(gen, generator.assembly.splitlines()))

        sim = Simulator(m)
        def process():

            index = simulator.pc.CIA.value//4
            while index < len(instructions):
                ins, code = instructions[index]

                print("0x{:X}".format(ins & 0xffffffff))
                print(code)

                yield instruction.eq(ins)
                yield Delay(1e-6)

                opname = code.split(' ')[0]
                yield from simulator.call(opname)
                index = simulator.pc.CIA.value//4


        sim.add_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()

        return simulator

    def test_0_cmp(self):
        lst = ["addi 6, 0, 0x10",
               "addi 7, 0, 0x05",
               "subf. 1, 6, 7",
               "cmp cr2, 1, 6, 7",
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1])

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

    def test_0_ldst_widths(self):
        lst = ["addis 1, 0, 0xdead",
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

    @unittest.skip("broken")
    def test_mulli(self):
        lst = ["addi 1, 0, 3",
               "mulli 1, 1, 2"
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1])

    def run_tst_program(self, prog, reglist):
        import sys
        simulator = self.run_tst(prog)
        prog.reset()
        with run_program(prog) as q:
            self.qemu_register_compare(simulator, q, reglist)
            self.qemu_mem_compare(simulator, q, reglist)
        print(simulator.gpr.dump())

    def qemu_mem_compare(self, sim, qemu, regs):
        addr = 0x1000
        qmemdump = qemu.get_mem(addr, 16)
        for i in range(len(qmemdump)):
            s = hex(int(qmemdump[i]))
            print ("qemu mem %06x %s" % (addr+i*8, s))
        for k, v in sim.mem.mem.items():
            print ("sim      %06x %016x" % (k, v))
        for k, v in sim.mem.mem.items():
            self.assertEqual(int(qmemdump[(k-0x200)//8]), v) # magic constant??

    def qemu_register_compare(self, sim, qemu, regs):
        qpc, qxer, qcr = qemu.get_pc(), qemu.get_xer(), qemu.get_cr()
        sim_cr = sim.cr.get_range().value
        sim_pc = sim.pc.CIA.value
        sim_xer = sim.spr['XER'].value
        print("qemu pc", hex(qpc))
        print("qemu cr", hex(qcr))
        print("qemu xer", bin(qxer))
        print("sim pc", hex(sim.pc.CIA.value))
        print("sim cr", hex(sim_cr))
        print("sim xer", hex(sim_xer))
        self.assertEqual(qcr, sim_cr)
        for reg in regs:
            qemu_val = qemu.get_register(reg)
            sim_val = sim.gpr(reg).value
            self.assertEqual(qemu_val, sim_val)


if __name__ == "__main__":
    unittest.main()
