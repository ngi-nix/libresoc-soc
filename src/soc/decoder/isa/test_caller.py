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
from soc.decoder.isa.all import ISA


class Register:
    def __init__(self, num):
        self.num = num


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, generator, initial_regs):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        simulator = ISA(pdecode2, initial_regs)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)
        gen = generator.generate_instructions()

        def process():
            instructions = list(zip(gen, generator.assembly.splitlines()))

            index = simulator.pc.CIA.value//4
            while index < len(instructions):
                ins, code = instructions[index]

                print("0x{:X}".format(ins & 0xffffffff))
                print(code)

                # ask the decoder to decode this binary data (endian'd)
                yield pdecode2.dec.bigendian.eq(0)  # little / big?
                yield instruction.eq(ins)          # raw binary instr.
                yield Delay(1e-6)
                opname = code.split(' ')[0]
                yield from simulator.call(opname)
                index = simulator.pc.CIA.value//4

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
            sim = self.run_tst_program(program, initial_regs)
            self.assertEqual(sim.gpr(1), SelectableInt(0x5555, 64))

    def test_addi(self):
        lst = ["addi 3, 0, 0x1234",
               "addi 2, 0, 0x4321",
               "add  1, 3, 2"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            print(sim.gpr(1))
            self.assertEqual(sim.gpr(1), SelectableInt(0x5555, 64))

    def test_load_store(self):
        lst = ["addi 1, 0, 0x0010",
               "addi 2, 0, 0x1234",
               "stw 2, 0(1)",
               "lwz 3, 0(1)"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            print(sim.gpr(1))
            self.assertEqual(sim.gpr(3), SelectableInt(0x1234, 64))

    def test_addpcis(self):
        lst = ["addpcis 1, 0x1",
               "addpcis 2, 0x1",
               "addpcis 3, 0x1"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            self.assertEqual(sim.gpr(1), SelectableInt(0x10004, 64))
            self.assertEqual(sim.gpr(2), SelectableInt(0x10008, 64))
            self.assertEqual(sim.gpr(3), SelectableInt(0x1000c, 64))

    def test_branch(self):
        lst = ["ba 0xc",             # branch to line 4
               "addi 1, 0, 0x1234",  # Should never execute
               "ba 0x1000",          # exit the program
               "addi 2, 0, 0x1234",  # line 4
               "ba 0x8"]             # branch to line 3
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            self.assertEqual(sim.pc.CIA, SelectableInt(0x1000, 64))
            self.assertEqual(sim.gpr(1), SelectableInt(0x0, 64))
            self.assertEqual(sim.gpr(2), SelectableInt(0x1234, 64))

    def test_branch_link(self):
        lst = ["bl 0xc",
               "addi 2, 1, 0x1234",
               "ba 0x1000",
               "addi 1, 0, 0x1234",
               "bclr 20, 0, 0"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            self.assertEqual(sim.spr['LR'], SelectableInt(0x4, 64))

    def test_branch_ctr(self):
        lst = ["addi 1, 0, 0x10",    # target of jump
               "mtspr 9, 1",         # mtctr 1
               "bcctr 20, 0, 0",     # bctr
               "addi 2, 0, 0x1",     # should never execute
               "addi 1, 0, 0x1234"]  # target of ctr
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            self.assertEqual(sim.spr['CTR'], SelectableInt(0x10, 64))
            self.assertEqual(sim.gpr(1), SelectableInt(0x1234, 64))
            self.assertEqual(sim.gpr(2), SelectableInt(0, 64))

    def test_branch_cond(self):
        for i in [0, 10]:
            lst = [f"addi 1, 0, {i}",  # set r1 to i
                "cmpi cr0, 1, 1, 10",  # compare r1 with 10 and store to cr0
                "bc 12, 2, 0x8",       # beq 0x8 -
                                       # branch if r1 equals 10 to the nop below
                "addi 2, 0, 0x1234",   # if r1 == 10 this shouldn't execute
                "or 0, 0, 0"]          # branch target
            with Program(lst) as program:
                sim = self.run_tst_program(program)
                if i == 10:
                    self.assertEqual(sim.gpr(2), SelectableInt(0, 64))
                else:
                    self.assertEqual(sim.gpr(2), SelectableInt(0x1234, 64))

    def test_branch_loop(self):
        lst = ["addi 1, 0, 0",
               "addi 1, 0, 0",
               "addi 1, 1, 1",
               "add  2, 2, 1",
               "cmpi cr0, 1, 1, 10",
               "bc 12, 0, -0xc"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            # Verified with qemu
            self.assertEqual(sim.gpr(2), SelectableInt(0x37, 64))

    def test_branch_loop_ctr(self):
        lst = ["addi 1, 0, 0",
               "addi 2, 0, 7",
               "mtspr 9, 2",    # set ctr to 7
               "addi 1, 1, 5",
               "bc 16, 0, -0x4"]  # bdnz to the addi above
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            # Verified with qemu
            self.assertEqual(sim.gpr(1), SelectableInt(0x23, 64))



    def test_add_compare(self):
        lst = ["addis 1, 0, 0xffff",
               "addis 2, 0, 0xffff",
               "add. 1, 1, 2",
               "mfcr 3"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            # Verified with QEMU
            self.assertEqual(sim.gpr(3), SelectableInt(0x80000000, 64))

    def test_cmp(self):
        lst = ["addis 1, 0, 0xffff",
               "addis 2, 0, 0xffff",
               "cmp cr0, 0, 1, 2",
               "mfcr 3"]
        with Program(lst) as program:
            sim = self.run_tst_program(program)
            self.assertEqual(sim.gpr(3), SelectableInt(0x20000000, 64))

    def test_slw(self):
        lst = ["slw 1, 3, 2"]
        initial_regs = [0] * 32
        initial_regs[3] = 0xdeadbeefcafebabe
        initial_regs[2] = 5
        with Program(lst) as program:
            sim = self.run_tst_program(program, initial_regs)
            self.assertEqual(sim.gpr(1), SelectableInt(0x5fd757c0, 32))

    def test_srw(self):
        lst = ["srw 1, 3, 2"]
        initial_regs = [0] * 32
        initial_regs[3] = 0xdeadbeefcafebabe
        initial_regs[2] = 5
        with Program(lst) as program:
            sim = self.run_tst_program(program, initial_regs)
            self.assertEqual(sim.gpr(1), SelectableInt(0x657f5d5, 32))

    def test_mtcrf(self):
        for i in range(4):
            # 0x76540000 gives expected (3+4) (2+4) (1+4) (0+4) for
            #     i=0, 1, 2, 3
            # The positions of the CR fields have been verified using
            # QEMU and 'cmp crx, a, b' instructions
            lst = ["addis 1, 0, 0x7654",
                   "mtcrf %d, 1" % (1 << (7-i)),
                   ]
            with Program(lst) as program:
                sim = self.run_tst_program(program)
            print("cr", sim.cr)
            expected = (7-i)
            # check CR itself
            self.assertEqual(sim.cr, SelectableInt(expected << ((7-i)*4), 32))
            # check CR[0]/1/2/3 as well
            print("cr%d", sim.crl[i])
            self.assertTrue(SelectableInt(expected, 4) == sim.crl[i])

    def run_tst_program(self, prog, initial_regs=[0] * 32):
        simulator = self.run_tst(prog, initial_regs)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
