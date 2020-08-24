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
from soc.config.endian import bigendian

from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2

from soc.simple.issuer import TestIssuer
from soc.experiment.compalu_multi import find_ok  # hack

from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.test.test_core import (setup_regs, check_regs,
                                       wait_for_busy_clear,
                                       wait_for_busy_hi)
from soc.fu.compunits.test.test_compunit import (setup_test_memory,
                                                 check_sim_memory)
from soc.debug.dmi import DBGCore, DBGCtrl, DBGStat

# test with ALU data and Logical data
from soc.fu.alu.test.test_pipe_caller import ALUTestCase
from soc.fu.div.test.test_pipe_caller import DivTestCases
from soc.fu.logical.test.test_pipe_caller import LogicalTestCase
#from soc.fu.shift_rot.test.test_pipe_caller import ShiftRotTestCase
from soc.fu.cr.test.test_pipe_caller import CRTestCase
#from soc.fu.branch.test.test_pipe_caller import BranchTestCase
#from soc.fu.spr.test.test_pipe_caller import SPRTestCase
from soc.fu.ldst.test.test_pipe_caller import LDSTTestCase
from soc.simulator.test_sim import (GeneralTestCases, AttnTestCase)
#from soc.simulator.test_helloworld_sim import HelloTestCases


def setup_i_memory(imem, startaddr, instructions):
    mem = imem
    print("insn before, init mem", mem.depth, mem.width, mem,
          len(instructions))
    for i in range(mem.depth):
        yield mem._array[i].eq(0)
    yield Settle()
    startaddr //= 4  # instructions are 32-bit
    if mem.width == 32:
        mask = ((1 << 32)-1)
        for ins in instructions:
            if isinstance(ins, tuple):
                insn, code = ins
            else:
                insn, code = ins, ''
            insn = insn & 0xffffffff
            yield mem._array[startaddr].eq(insn)
            yield Settle()
            if insn != 0:
                print("instr: %06x 0x%x %s" % (4*startaddr, insn, code))
            startaddr += 1
            startaddr = startaddr & mask
        return

    # 64 bit
    mask = ((1 << 64)-1)
    for ins in instructions:
        if isinstance(ins, tuple):
            insn, code = ins
        else:
            insn, code = ins, ''
        insn = insn & 0xffffffff
        msbs = (startaddr >> 1) & mask
        val = yield mem._array[msbs]
        if insn != 0:
            print("before set", hex(4*startaddr),
                  hex(msbs), hex(val), hex(insn))
        lsb = 1 if (startaddr & 1) else 0
        val = (val | (insn << (lsb*32)))
        val = val & mask
        yield mem._array[msbs].eq(val)
        yield Settle()
        if insn != 0:
            print("after  set", hex(4*startaddr), hex(msbs), hex(val))
            print("instr: %06x 0x%x %s %08x" % (4*startaddr, insn, code, val))
        startaddr += 1
        startaddr = startaddr & mask


def set_dmi(dmi, addr, data):
    yield dmi.req_i.eq(1)
    yield dmi.addr_i.eq(addr)
    yield dmi.din.eq(data)
    yield dmi.we_i.eq(1)
    while True:
        ack = yield dmi.ack_o
        if ack:
            break
        yield
    yield
    yield dmi.req_i.eq(0)
    yield dmi.addr_i.eq(0)
    yield dmi.din.eq(0)
    yield dmi.we_i.eq(0)
    yield


def get_dmi(dmi, addr):
    yield dmi.req_i.eq(1)
    yield dmi.addr_i.eq(addr)
    yield dmi.din.eq(0)
    yield dmi.we_i.eq(0)
    while True:
        ack = yield dmi.ack_o
        if ack:
            break
        yield
    yield # wait one
    data = yield dmi.dout # get data after ack valid for 1 cycle
    yield dmi.req_i.eq(0)
    yield dmi.addr_i.eq(0)
    yield dmi.we_i.eq(0)
    yield
    return data


class TestRunner(FHDLTestCase):
    def __init__(self, tst_data):
        super().__init__("run_all")
        self.test_data = tst_data

    def run_all(self):
        m = Module()
        comb = m.d.comb
        pc_i = Signal(32)

        pspec = TestMemPspec(ldst_ifacetype='test_bare_wb',
                             imem_ifacetype='test_bare_wb',
                             addr_wid=48,
                             mask_wid=8,
                             imem_reg_wid=64,
                             #wb_data_width=32,
                             reg_wid=64)
        m.submodules.issuer = issuer = TestIssuer(pspec)
        imem = issuer.imem._get_memory()
        core = issuer.core
        dmi = issuer.dbg.dmi
        pdecode2 = issuer.pdecode2
        l0 = core.l0

        # copy of the decoder for simulator
        simdec = create_pdecode()
        simdec2 = PowerDecode2(simdec)
        m.submodules.simdec2 = simdec2  # pain in the neck

        comb += issuer.pc_i.data.eq(pc_i)

        # nmigen Simulation
        sim = Simulator(m)
        sim.add_clock(1e-6)

        def process():

            # start in stopped
            yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.STOP)
            yield
            yield

            for test in self.test_data:

                # pull a reset
                #yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.RESET)

                # set up bigendian (TODO: don't do this, use MSR)
                yield issuer.core_bigendian_i.eq(bigendian)
                yield Settle()

                yield
                yield
                yield
                yield

                print(test.name)
                program = test.program
                self.subTest(test.name)
                print("regs", test.regs)
                print("sprs", test.sprs)
                print("cr", test.cr)
                print("mem", test.mem)
                print("msr", test.msr)
                print("assem", program.assembly)
                gen = list(program.generate_instructions())
                insncode = program.assembly.splitlines()
                instructions = list(zip(gen, insncode))
                sim = ISA(simdec2, test.regs, test.sprs, test.cr, test.mem,
                          test.msr,
                          initial_insns=gen, respect_pc=True,
                          disassembly=insncode,
                          bigendian=bigendian)

                pc = 0  # start address
                counter = 0 # test to pause/start

                yield from setup_i_memory(imem, pc, instructions)
                yield from setup_test_memory(l0, sim)
                yield from setup_regs(pdecode2, core, test)

                yield pc_i.eq(pc)
                yield issuer.pc_i.ok.eq(1)
                yield

                print("instructions", instructions)

                index = sim.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("instruction: 0x{:X}".format(ins & 0xffffffff))
                    print(index, code)

                    if counter == 0:
                        # start the core
                        yield
                        yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.START)
                        yield issuer.pc_i.ok.eq(0)  # no change PC after this
                        yield
                        yield

                    counter = counter + 1

                    # wait until executed
                    yield from wait_for_busy_hi(core)
                    yield from wait_for_busy_clear(core)

                    # set up simulated instruction (in simdec2)
                    try:
                        yield from sim.setup_one()
                    except KeyError:  # indicates instruction not in imem: stop
                        break
                    yield Settle()

                    # call simulated operation
                    print("sim", code)
                    yield from sim.execute_one()
                    yield Settle()
                    index = sim.pc.CIA.value//4

                    terminated = yield issuer.dbg.terminated_o
                    print("terminated", terminated)

                    if index >= len(instructions):
                        print ("index over, send dmi stop")
                        # stop at end
                        yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.STOP)
                        yield
                        yield

                    # wait one cycle for registers to settle
                    yield

                    # register check
                    yield from check_regs(self, sim, core, test, code)

                    # Memory check
                    yield from check_sim_memory(self, l0, sim, code)

                    terminated = yield issuer.dbg.terminated_o
                    print("terminated(2)", terminated)
                    if terminated:
                        break

                # stop at end
                yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.STOP)
                yield
                yield

                # test of dmi reg get
                for int_reg in range(32):
                    yield from set_dmi(dmi, DBGCore.GSPR_IDX, int_reg) 
                    value = yield from get_dmi(dmi, DBGCore.GSPR_DATA)

                    print ("after test %s reg %2d value %x" % \
                                (test.name, int_reg, value))

        sim.add_sync_process(process)
        with sim.write_vcd("issuer_simulator.vcd",
                           traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    # suite.addTest(TestRunner(HelloTestCases.test_data))
    suite.addTest(TestRunner(DivTestCases().test_data))
    # suite.addTest(TestRunner(AttnTestCase.test_data))
    suite.addTest(TestRunner(GeneralTestCases.test_data))
    suite.addTest(TestRunner(LDSTTestCase().test_data))
    suite.addTest(TestRunner(CRTestCase().test_data))
    # suite.addTest(TestRunner(ShiftRotTestCase.test_data))
    suite.addTest(TestRunner(LogicalTestCase().test_data))
    suite.addTest(TestRunner(ALUTestCase().test_data))
    # suite.addTest(TestRunner(BranchTestCase.test_data))
    # suite.addTest(TestRunner(SPRTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
