import random
from soc.fu.shift_rot.pipe_data import ShiftRotPipeSpec
from soc.fu.shift_rot.pipeline import ShiftRotBasePipe
from openpower.test.common import TestAccumulatorBase, TestCase, ALUHelpers
from openpower.endian import bigendian
from openpower.decoder.isa.all import ISA
from openpower.simulator.program import Program
from openpower.decoder.power_enums import (XER_bits, Function, CryIn)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_decoder import (create_pdecode)
import unittest
from nmigen.cli import rtlil
from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from openpower.test.shift_rot.shift_rot_cases import ShiftRotTestCase


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to ShiftRotFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
    yield from ALUHelpers.get_sim_int_rc(res, sim, dec2)  # RC
    yield from ALUHelpers.get_rd_sim_xer_ca(res, sim, dec2)  # XER.ca
    yield from ALUHelpers.get_sim_xer_so(res, sim, dec2)  # XER.so

    print("alu get_cu_inputs", res)

    return res


def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)
    yield from ALUHelpers.set_int_rc(alu, dec2, inp)
    yield from ALUHelpers.set_xer_ca(alu, dec2, inp)
    yield from ALUHelpers.set_xer_so(alu, dec2, inp)


# This test bench is a bit different than is usual. Initially when I
# was writing it, I had all of the tests call a function to create a
# device under test and simulator, initialize the dut, run the
# simulation for ~2 cycles, and assert that the dut output what it
# should have. However, this was really slow, since it needed to
# create and tear down the dut and simulator for every test case.

# Now, instead of doing that, every test case in ShiftRotTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class ShiftRotIlangCase(TestAccumulatorBase):

    def case_ilang(self):
        pspec = ShiftRotPipeSpec(id_wid=2)
        alu = ShiftRotBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("shift_rot_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def execute(self, alu, instruction, pdecode2, test):
        program = test.program
        simulator = ISA(pdecode2, test.regs, test.sprs, test.cr,
                        test.mem, test.msr,
                        bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))

        index = simulator.pc.CIA.value//4
        while index < len(instructions):
            ins, code = instructions[index]

            print("0x{:X}".format(ins & 0xffffffff))
            print(code)

            # ask the decoder to decode this binary data (endian'd)
            yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()
            fn_unit = yield pdecode2.e.do.fn_unit
            self.assertEqual(fn_unit, Function.SHIFT_ROT.value)
            yield from set_alu_inputs(alu, pdecode2, simulator)

            # set valid for one cycle, propagate through pipeline...
            yield alu.p.valid_i.eq(1)
            yield
            yield alu.p.valid_i.eq(0)

            opname = code.split(' ')[0]
            yield from simulator.call(opname)
            index = simulator.pc.CIA.value//4

            vld = yield alu.n.valid_o
            while not vld:
                yield
                vld = yield alu.n.valid_o
            yield
            alu_out = yield alu.n.data_o.o.data

            yield from self.check_alu_outputs(alu, pdecode2,
                                              simulator, code)
            yield Settle()

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        fn_name = "SHIFT_ROT"
        opkls = ShiftRotPipeSpec.opsubsetkls

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(None, opkls, fn_name)
        pdecode = pdecode2.dec

        pspec = ShiftRotPipeSpec(id_wid=2)
        m.submodules.alu = alu = ShiftRotBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
                print(test.name)
                program = test.program
                with self.subTest(test.name):
                    yield from self.execute(alu, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("shift_rot_simulator.vcd"):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code):

        rc = yield dec2.e.do.rc.rc
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print("check extra output", repr(code), cridx_ok, cridx)
        if rc:
            self.assertEqual(cridx, 0, code)

        sim_o = {}
        res = {}

        yield from ALUHelpers.get_cr_a(res, alu, dec2)
        yield from ALUHelpers.get_xer_ca(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)

        print ("hw outputs", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ca(sim_o, sim, dec2)

        print ("sim outputs", sim_o)

        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
        ALUHelpers.check_xer_ca(self, res, sim_o, code)
        ALUHelpers.check_int_o(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(ShiftRotTestCase().test_data))
    suite.addTest(TestRunner(ShiftRotIlangCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
