from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
import unittest
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, MicrOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form, SPR,
                                     get_signal_name, get_csv)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.simulator.qemu import run_program
from soc.decoder.isa.all import ISA
from soc.fu.test.common import TestCase
from soc.config.endian import bigendian


class AttnTestCase(FHDLTestCase):
    test_data = []

    def __init__(self, name="general"):
        super().__init__(name)
        self.test_name = name

    def test_0_attn(self):
        """simple test of attn.  program is 4 long: should halt at 2nd op
        """
        lst = ["addi 6, 0, 0x10",
               "attn",
               "subf. 1, 6, 7",
               "cmp cr2, 1, 6, 7",
               ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1])

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None,
                        initial_mem=None):
        initial_regs = [0] * 32
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs, 0,
                      initial_mem, 0)
        self.test_data.append(tc)


class GeneralTestCases(FHDLTestCase):
    test_data = []

    def __init__(self, name="general"):
        super().__init__(name)
        self.test_name = name

    @unittest.skip("disable")
    def test_0_cmp(self):
        lst = ["addi 6, 0, 0x10",
               "addi 7, 0, 0x05",
               "subf. 1, 6, 7",
               "cmp cr2, 1, 6, 7",
               ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1])

    @unittest.skip("disable")
    def test_example(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "add  3, 1, 2",
               "and  4, 1, 2"]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3, 4])

    @unittest.skip("disable")
    def test_ldst(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "stw  1, 0(2)",
               "lwz  3, 0(2)"
               ]
        initial_mem = {0x1230: (0x5432123412345678, 8),
                       0x1238: (0xabcdef0187654321, 8),
                       }
        with Program(lst, bigendian) as program:
            self.run_tst_program(program,
                                 [1, 2, 3],
                                 initial_mem)

    @unittest.skip("disable")
    def test_ld_rev_ext(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "addi 4, 0, 0x40",
               "stw  1, 0x40(2)",
               "lwbrx  3, 4, 2"]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3])

    @unittest.skip("disable")
    def test_st_rev_ext(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "addi 4, 0, 0x40",
               "stwbrx  1, 4, 2",
               "lwzx  3, 4, 2"]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3])

    @unittest.skip("disable")
    def test_ldst_extended(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "addi 4, 0, 0x40",
               "stw  1, 0x40(2)",
               "lwzx  3, 4, 2"]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3])

    @unittest.skip("disable")
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
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3, 4, 5])

    @unittest.skip("disable")
    def test_sub(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "subf 3, 1, 2",
               "subfic 4, 1, 0x1337",
               "neg 5, 1"]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3, 4, 5])

    @unittest.skip("disable")
    def test_add_with_carry(self):
        lst = ["addi 1, 0, 5",
               "neg 1, 1",
               "addi 2, 0, 7",
               "neg 2, 2",
               "addc 3, 2, 1",
               "addi 3, 3, 1"
               ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3])

    @unittest.skip("disable")
    def test_addis(self):
        lst = ["addi 1, 0, 0x0FFF",
               "addis 1, 1, 0x0F"
               ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1])

    @unittest.skip("broken")
    def test_mulli(self):
        lst = ["addi 1, 0, 3",
               "mulli 1, 1, 2"
               ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1])

    @unittest.skip("disable")
    def test_2_load_store(self):
        lst = ["addi 1, 0, 0x1004",
               "addi 2, 0, 0x1008",
               "addi 3, 0, 0x00ee",
               "stb 3, 1(2)",
               "lbz 4, 1(2)",
               ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1004
        initial_regs[2] = 0x1008
        initial_regs[3] = 0x00ee
        initial_mem = {0x1000: (0x5432123412345678, 8),
                       0x1008: (0xabcdef0187654321, 8),
                       0x1020: (0x1828384822324252, 8),
                       }
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [3, 4], initial_mem)

    @unittest.skip("disable")
    def test_3_load_store(self):
        lst = ["addi 1, 0, 0x1004",
               "addi 2, 0, 0x1002",
               "addi 3, 0, 0x15eb",
               "sth 4, 0(2)",
               "lhz 4, 0(2)"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1004
        initial_regs[2] = 0x1002
        initial_regs[3] = 0x15eb
        initial_mem = {0x1000: (0x5432123412345678, 8),
                       0x1008: (0xabcdef0187654321, 8),
                       0x1020: (0x1828384822324252, 8),
                       }
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 2, 3, 4], initial_mem)

    def test_nop(self):
        lst = ["addi 1, 0, 0x1004",
               "ori 0,0,0", # "preferred" form of nop
               "addi 3, 0, 0x15eb",
              ]
        initial_regs = [0] * 32
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [1, 3])

    @unittest.skip("disable")
    def test_zero_illegal(self):
        lst = bytes([0x10,0x00,0x20,0x39,
                     0x0,0x0,0x0,0x0,
                     0x0,0x0,0x0,0x0 ])
        disassembly = ["addi 9, 0, 0x10",
                       "nop", # not quite
                       "nop"] # not quite
        initial_regs = [0] * 32
        with Program(lst, bigendian) as program:
            program.assembly = '\n'.join(disassembly) + '\n' # XXX HACK!
            self.run_tst_program(program, [1, 3])

    def test_loop(self):
        """in godbolt.org:
        register unsigned long i asm ("r12");
        void square(void) {
            i = 5;
            do {
                i = i - 1;
            } while (i != 0);
        }
        """
        lst = ["addi 9, 0, 0x10",  # i = 16
               "addi 9,9,-1",    # i = i - 1
               "cmpi 0,1,9,12",     # compare 9 to value 0, store in CR2
               "bc 4,0,-8"         # branch if CR2 "test was != 0"
               ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [9], initial_mem={})

    def test_30_addis(self):
        lst = [  # "addi 0, 0, 5",
            "addis 12, 0, 0",
        ]
        with Program(lst, bigendian) as program:
            self.run_tst_program(program, [12])

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None,
                        initial_mem=None):
        initial_regs = [0] * 32
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs, 0,
                      initial_mem, 0)
        self.test_data.append(tc)


class DecoderBase:

    def run_tst(self, generator, initial_mem=None, initial_pc=0):
        m = Module()
        comb = m.d.comb

        gen = list(generator.generate_instructions())
        insn_code = generator.assembly.splitlines()
        instructions = list(zip(gen, insn_code))

        pdecode = create_pdecode()
        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        # place program at requested address
        gen = (initial_pc, gen)

        simulator = ISA(pdecode2, [0] * 32, {}, 0, initial_mem, 0,
                        initial_insns=gen, respect_pc=True,
                        disassembly=insn_code,
                        initial_pc=initial_pc,
                        bigendian=bigendian)

        sim = Simulator(m)

        def process():
            # yield pdecode2.dec.bigendian.eq(bigendian)
            yield Settle()

            while True:
                try:
                    yield from simulator.setup_one()
                except KeyError:  # indicates instruction not in imem: stop
                    break
                yield Settle()
                yield from simulator.execute_one()
                yield Settle()

        sim.add_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()

        return simulator

    def run_tst_program(self, prog, reglist, initial_mem=None,
                        extra_break_addr=None):
        import sys
        simulator = self.run_tst(prog, initial_mem=initial_mem,
                                 initial_pc=0x20000000)
        prog.reset()
        with run_program(prog, initial_mem, extra_break_addr,
                         bigendian=bigendian) as q:
            self.qemu_register_compare(simulator, q, reglist)
            self.qemu_mem_compare(simulator, q, True)
        print(simulator.gpr.dump())

    def qemu_mem_compare(self, sim, qemu, check=True):
        if False:  # disable convenient large interesting debugging memory dump
            addr = 0x0
            qmemdump = qemu.get_mem(addr, 2048)
            for i in range(len(qmemdump)):
                s = hex(int(qmemdump[i]))
                print("qemu mem %06x %s" % (addr+i*8, s))
        for k, v in sim.mem.mem.items():
            qmemdump = qemu.get_mem(k*8, 8)
            s = hex(int(qmemdump[0]))[2:]
            print("qemu mem %06x %16s" % (k*8, s))
        for k, v in sim.mem.mem.items():
            print("sim mem  %06x %016x" % (k*8, v))
        if not check:
            return
        for k, v in sim.mem.mem.items():
            qmemdump = qemu.get_mem(k*8, 1)
            self.assertEqual(int(qmemdump[0]), v)

    def qemu_register_compare(self, sim, qemu, regs):
        qpc, qxer, qcr = qemu.get_pc(), qemu.get_xer(), qemu.get_cr()
        sim_cr = sim.cr.get_range().value
        sim_pc = sim.pc.CIA.value
        sim_xer = sim.spr['XER'].value
        print("qemu pc", hex(qpc))
        print("qemu cr", hex(qcr))
        print("qemu xer", bin(qxer))
        print("sim nia", hex(sim.pc.NIA.value))
        print("sim pc", hex(sim.pc.CIA.value))
        print("sim cr", hex(sim_cr))
        print("sim xer", hex(sim_xer))
        self.assertEqual(qpc, sim_pc)
        for reg in regs:
            qemu_val = qemu.get_register(reg)
            sim_val = sim.gpr(reg).value
            self.assertEqual(qemu_val, sim_val,
                             "expect %x got %x" % (qemu_val, sim_val))
        self.assertEqual(qcr, sim_cr)


class DecoderTestCase(DecoderBase, GeneralTestCases):
    pass


if __name__ == "__main__":
    unittest.main()
