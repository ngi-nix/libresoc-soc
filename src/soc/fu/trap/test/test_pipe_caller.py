from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, InternalOp, CryIn)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA


from soc.fu.test.common import (TestCase, ALUHelpers)
from soc.fu.trap.pipeline import TrapBasePipe
from soc.fu.trap.pipe_data import TrapPipeSpec
import random


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to TrapFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2) # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2) # RB
    yield from ALUHelpers.get_sim_fast_spr1(res, sim, dec2) # SPR1
    yield from ALUHelpers.get_sim_fast_spr2(res, sim, dec2) # SPR2
    ALUHelpers.get_sim_cia(res, sim, dec2) # PC
    ALUHelpers.get_sim_msr(res, sim, dec2) # MSR

    print ("alu get_cu_inputs", res)

    return res



def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)
    yield from ALUHelpers.set_fast_spr1(alu, dec2, inp) # SPR1
    yield from ALUHelpers.set_fast_spr2(alu, dec2, inp) # SPR1

    yield from ALUHelpers.set_cia(alu, dec2, inp)
    yield from ALUHelpers.set_msr(alu, dec2, inp)


# This test bench is a bit different than is usual. Initially when I
# was writing it, I had all of the tests call a function to create a
# device under test and simulator, initialize the dut, run the
# simulation for ~2 cycles, and assert that the dut output what it
# should have. However, this was really slow, since it needed to
# create and tear down the dut and simulator for every test case.

# Now, instead of doing that, every test case in TrapTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class TrapTestCase(FHDLTestCase):
    test_data = []

    def __init__(self, name):
        super().__init__(name)
        self.test_name = name

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None):
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs)
        self.test_data.append(tc)

    def test_1_rfid(self):
        lst = ["rfid"]
        initial_regs = [0] * 32
        initial_regs[1] = 1
        initial_sprs = {'SRR0': 0x12345678, 'SRR1': 0x5678}
        self.run_tst_program(Program(lst), initial_regs, initial_sprs)

    def test_0_trap_eq_imm(self):
        insns = ["twi", "tdi"]
        for i in range(2):
            choice = random.choice(insns)
            lst = [f"{choice} 4, 1, %d" % i] # TO=4: trap equal
            initial_regs = [0] * 32
            initial_regs[1] = 1
            self.run_tst_program(Program(lst), initial_regs)

    def test_0_trap_eq(self):
        insns = ["tw", "td"]
        for i in range(2):
            choice = insns[i]
            lst = [f"{choice} 4, 1, 2"] # TO=4: trap equal
            initial_regs = [0] * 32
            initial_regs[1] = 1
            initial_regs[2] = 1
            self.run_tst_program(Program(lst), initial_regs)

    def test_ilang(self):
        pspec = TrapPipeSpec(id_wid=2)
        alu = TrapBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("trap_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(FHDLTestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = TrapPipeSpec(id_wid=2)
        m.submodules.alu = alu = TrapBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.p.valid_i.eq(1)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)
        def process():
            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                                test.mem, test.msr)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                pc = sim.pc.CIA.value
                index = pc//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("pc %08x instr: %08x" % (pc, ins & 0xffffffff))
                    print(code)
                    if 'XER' in sim.spr:
                        so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                        ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                        ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                        print ("before: so/ov/32", so, ov, ov32)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    fn_unit = yield pdecode2.e.do.fn_unit
                    self.assertEqual(fn_unit, Function.TRAP.value)
                    yield from set_alu_inputs(alu, pdecode2, sim)
                    yield
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    pc = sim.pc.CIA.value
                    index = pc//4
                    print("pc after %08x" % (pc))

                    vld = yield alu.n.valid_o
                    while not vld:
                        yield
                        vld = yield alu.n.valid_o
                    yield

                    yield from self.check_alu_outputs(alu, pdecode2, sim, code)

        sim.add_sync_process(process)
        with sim.write_vcd("alu_simulator.vcd", "simulator.gtkw",
                            traces=[]):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code):

        rc = yield dec2.e.do.rc.data
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print ("check extra output", repr(code), cridx_ok, cridx)
        if rc:
            self.assertEqual(cridx, 0, code)

        sim_o = {}
        res = {}

        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_fast_spr1(res, alu, dec2)
        yield from ALUHelpers.get_fast_spr2(res, alu, dec2)
        yield from ALUHelpers.get_nia(res, alu, dec2)
        yield from ALUHelpers.get_msr(res, alu, dec2)

        print ("output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr1(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr2(sim_o, sim, dec2)
        ALUHelpers.get_sim_nia(sim_o, sim, dec2)
        ALUHelpers.get_sim_msr(sim_o, sim, dec2)

        print ("sim output", sim_o)

        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_fast_spr1(self, res, sim_o, code)
        ALUHelpers.check_fast_spr2(self, res, sim_o, code)
        ALUHelpers.check_nia(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(TrapTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
