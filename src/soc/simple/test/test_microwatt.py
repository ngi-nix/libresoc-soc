from openpower.simulator.program import Program
from openpower.test.common import TestCase

import unittest

from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase

from soc.simple.issuer import TestIssuer
from openpower.endian import bigendian


from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.test.test_core import (setup_regs, check_regs,
                                       wait_for_busy_clear,
                                       wait_for_busy_hi)
from soc.fu.compunits.test.test_compunit import (setup_tst_memory,
                                                 check_sim_memory,
                                                 get_l0_mem)

from soc.simple.test.test_runner import setup_i_memory

import sys
sys.setrecursionlimit(10**6)


class BinaryTestCase(FHDLTestCase):
    test_data = []

    def __init__(self, name="general"):
        super().__init__(name)
        self.test_name = name

    @unittest.skip("a bit big")
    def test_binary(self):
        with Program("1.bin", bigendian) as program:
            self.run_tst_program(program)

    def test_binary(self):
        with Program("hello_world.bin", bigendian) as program:
            self.run_tst_program(program)

    def run_tst_program(self, prog):
        initial_regs = [0] * 32
        tc = TestCase(prog, self.test_name, initial_regs, None, 0,
                      None, 0,
                      do_sim=False)
        self.test_data.append(tc)


class TestRunner(FHDLTestCase):
    def __init__(self, tst_data):
        super().__init__("binary_runner")
        self.test_data = tst_data

    def binary_runner(self):
        m = Module()
        comb = m.d.comb
        go_insn_i = Signal()
        pc_i = Signal(32)
        pc_i_ok = Signal()

        pspec = TestMemPspec(ldst_ifacetype='test_bare_wb',
                             imem_ifacetype='test_bare_wb',
                             addr_wid=48,
                             mask_wid=8,
                             reg_wid=64,
                             imem_test_depth=32768,
                             dmem_test_depth=32768)
        m.submodules.issuer = issuer = TestIssuer(pspec)
        imem = issuer.imem._get_memory()
        core = issuer.core
        pdecode2 = core.pdecode2
        l0 = core.l0

        comb += issuer.pc_i.data.eq(pc_i)
        comb += issuer.pc_i.ok.eq(pc_i_ok)
        comb += issuer.go_insn_i.eq(go_insn_i)

        # nmigen Simulation
        sim = Simulator(m)
        sim.add_clock(1e-6)

        def process():

            for test in self.test_data:

                # get core going
                yield core.bigendian_i.eq(bigendian)
                yield core.core_start_i.eq(1)
                yield
                yield core.core_start_i.eq(0)
                yield Settle()

                print(test.name)
                program = test.program
                self.subTest(test.name)
                print("regs", test.regs)
                print("sprs", test.sprs)
                print("cr", test.cr)
                print("mem", test.mem)
                print("msr", test.msr)
                print("assem", program.assembly)
                instructions = list(program.generate_instructions())

                print("instructions", len(instructions))

                pc = 0  # start of memory

                yield from setup_i_memory(imem, pc, instructions)
                # blech!  put the same listing into the data memory
                data_mem = get_l0_mem(l0)
                yield from setup_i_memory(data_mem, pc, instructions)
                # yield from setup_tst_memory(l0, sim)
                yield from setup_regs(core, test)

                yield pc_i.eq(pc)
                yield pc_i_ok.eq(1)

                while True:

                    # start the instruction
                    yield go_insn_i.eq(1)
                    yield
                    yield pc_i_ok.eq(0)  # don't change PC from now on
                    yield go_insn_i.eq(0)      # and don't issue a new insn
                    yield from wait_for_busy_hi(core)
                    yield Settle()

                    # wait until executed
                    ins = yield core.raw_opcode_i
                    pc = yield issuer.pc_o
                    print("instruction: 0x%x @ %x" % (ins & 0xffffffff, pc))
                    yield from wait_for_busy_clear(core)

                    terminated = yield core.core_terminated_o
                    print("terminated", terminated)

                    terminated = yield core.core_terminated_o
                    if terminated:
                        break

            # register check
            # yield from check_regs(self, sim, core, test, code)

            # Memory check
            # yield from check_sim_memory(self, l0, sim, code)

        sim.add_sync_process(process)
        with sim.write_vcd("binary_issuer_simulator.vcd",
                           traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(BinaryTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
