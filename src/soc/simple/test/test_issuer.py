"""simple core test, runs instructions from a TestMemory

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""
from nmigen import Module, Signal, Cat
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import special_sprs
from soc.decoder.isa.all import ISA
from soc.decoder.power_enums import Function, XER_bits


from soc.simple.issuer import TestIssuer
from soc.experiment.compalu_multi import find_ok # hack

from soc.simple.test.test_core import (setup_regs, check_regs,
                                       wait_for_busy_clear,
                                       wait_for_busy_hi)
from soc.fu.compunits.test.test_compunit import (setup_test_memory,
                                                 check_sim_memory)

# test with ALU data and Logical data
from soc.fu.alu.test.test_pipe_caller import ALUTestCase
from soc.fu.logical.test.test_pipe_caller import LogicalTestCase
from soc.fu.shift_rot.test.test_pipe_caller import ShiftRotTestCase
from soc.fu.cr.test.test_pipe_caller import CRTestCase
from soc.fu.branch.test.test_pipe_caller import BranchTestCase
from soc.fu.ldst.test.test_pipe_caller import LDSTTestCase
from soc.simulator.test_sim import GeneralTestCases


def setup_i_memory(imem, startaddr, instructions):
    mem = imem
    print ("insn before, init mem", mem.depth, mem.width, mem)
    for i in range(mem.depth):
        yield mem._array[i].eq(0)
    yield Settle()
    startaddr //= 4 # instructions are 32-bit
    mask = ((1<<64)-1)
    for insn, code in instructions:
        msbs = (startaddr>>1) & mask
        val = yield mem._array[msbs]
        print ("before set", hex(startaddr), hex(msbs), hex(val))
        lsb = 1 if (startaddr & 1) else 0
        val = (val | (insn << (lsb*32))) & mask
        yield mem._array[msbs].eq(val)
        yield Settle()
        print ("after  set", hex(startaddr), hex(msbs), hex(val))
        print ("instr: %06x 0x%x %s %08x" % (4*startaddr, insn, code, val))
        startaddr += 1
        startaddr = startaddr & mask


class TestRunner(FHDLTestCase):
    def __init__(self, tst_data):
        super().__init__("run_all")
        self.test_data = tst_data

    def run_all(self):
        m = Module()
        comb = m.d.comb
        go_insn_i = Signal()
        pc_i = Signal(32)

        m.submodules.issuer = issuer = TestIssuer(ifacetype="test_bare_wb")
        imem = issuer.imem.mem.mem
        core = issuer.core
        pdecode2 = core.pdecode2
        l0 = core.l0

        comb += issuer.pc_i.data.eq(pc_i)
        comb += issuer.go_insn_i.eq(go_insn_i)

        # nmigen Simulation
        sim = Simulator(m)
        sim.add_clock(1e-6)

        def process():

            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                print ("regs", test.regs)
                print ("sprs", test.sprs)
                print ("cr", test.cr)
                print ("mem", test.mem)
                print ("msr", test.msr)
                print ("assem", program.assembly)
                gen = list(program.generate_instructions())
                insncode = program.assembly.splitlines()
                instructions = list(zip(gen, insncode))
                sim = ISA(pdecode2, test.regs, test.sprs, test.cr, test.mem,
                          test.msr,
                          initial_insns=gen, respect_pc=True,
                          disassembly=insncode)

                pc = 0 # start address

                yield from setup_i_memory(imem, pc, instructions)
                yield from setup_test_memory(l0, sim)
                yield from setup_regs(core, test)

                yield pc_i.eq(pc)
                yield issuer.pc_i.ok.eq(1)

                index = sim.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("instruction: 0x{:X}".format(ins & 0xffffffff))
                    print(index, code)

                    # start the instruction
                    yield go_insn_i.eq(1)
                    yield
                    yield issuer.pc_i.ok.eq(0) # don't change PC from now on
                    yield go_insn_i.eq(0)      # and don't issue a new insn

                    # wait until executed
                    yield from wait_for_busy_hi(core)
                    yield from wait_for_busy_clear(core)

                    print ("sim", code)
                    # call simulated operation
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    yield Settle()
                    index = sim.pc.CIA.value//4

                    # register check
                    yield from check_regs(self, sim, core, test, code)

                    # Memory check
                    yield from check_sim_memory(self, l0, sim, code)

        sim.add_sync_process(process)
        with sim.write_vcd("issuer_simulator.vcd",
                            traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(GeneralTestCases.test_data))
    suite.addTest(TestRunner(LDSTTestCase.test_data))
    suite.addTest(TestRunner(CRTestCase.test_data))
    suite.addTest(TestRunner(ShiftRotTestCase.test_data))
    suite.addTest(TestRunner(LogicalTestCase.test_data))
    suite.addTest(TestRunner(ALUTestCase.test_data))
    suite.addTest(TestRunner(BranchTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)

