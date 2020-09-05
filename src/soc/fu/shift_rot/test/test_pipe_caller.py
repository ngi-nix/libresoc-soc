import random
from soc.fu.shift_rot.pipe_data import ShiftRotPipeSpec
from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.shift_rot.pipeline import ShiftRotBasePipe
from soc.fu.test.common import TestAccumulatorBase, TestCase, ALUHelpers
from soc.config.endian import bigendian
from soc.decoder.isa.all import ISA
from soc.simulator.program import Program
from soc.decoder.selectable_int import SelectableInt
from soc.decoder.power_enums import (XER_bits, Function, CryIn)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.isa.caller import ISACaller, special_sprs
import unittest
from nmigen.cli import rtlil
from nmigen import Module, Signal
from nmigen.back.pysim import Delay, Settle
# NOTE: to use this (set to True), at present it is necessary to check
# out the cxxsim nmigen branch
cxxsim = False
if cxxsim:
    try:
        from nmigen.sim.cxxsim import Simulator
    except ImportError:
        print("nope, sorry, have to use nmigen cxxsim branch for now")
        cxxsim = False
        from nmigen.back.pysim import Simulator
else:
    from nmigen.back.pysim import Simulator


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


class ShiftRotTestCase(TestAccumulatorBase):

    def cse_0_proof_regression_rlwnm(self):
        lst = ["rlwnm 3, 1, 2, 16, 20"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7ffdbffb91b906b9
        initial_regs[2] = 31
        print(initial_regs[1], initial_regs[2])
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_regression_rldicr_0(self):
        lst = ["rldicr. 29, 19, 1, 21"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3f
        initial_regs[19] = 0x00000000ffff8000

        initial_sprs = {'XER': 0xe00c0000}

        self.add_case(Program(lst, bigendian), initial_regs,
                                initial_sprs=initial_sprs)

    def cse_regression_rldicr_1(self):
        lst = ["rldicr. 29, 19, 1, 21"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3f
        initial_regs[19] = 0x00000000ffff8000

        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_shift(self):
        insns = ["slw", "sld", "srw", "srd", "sraw", "srad"]
        for i in range(20):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, 63)
            print(initial_regs[1], initial_regs[2])
            self.add_case(Program(lst, bigendian), initial_regs)

    def cse_shift_arith(self):
        lst = ["sraw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = random.randint(0, (1 << 64)-1)
        initial_regs[2] = random.randint(0, 63)
        print(initial_regs[1], initial_regs[2])
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_sld_rb_too_big(self):
        lst = ["sld 3, 1, 4",
               ]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffffffff
        initial_regs[4] = 64 # too big, output should be zero
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_sld_rb_is_zero(self):
        lst = ["sld 3, 1, 4",
               ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x8000000000000000
        initial_regs[4] = 0 # no shift; output should equal input
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_shift_once(self):
        lst = ["slw 3, 1, 4",
               "slw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0x40
        initial_regs[4] = 0x00
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_rlwinm(self):
        for i in range(10):
            mb = random.randint(0, 31)
            me = random.randint(0, 31)
            sh = random.randint(0, 31)
            lst = [f"rlwinm 3, 1, {mb}, {me}, {sh}",
                   #f"rlwinm. 3, 1, {mb}, {me}, {sh}"
                   ]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def cse_rlwimi(self):
        lst = ["rlwimi 3, 1, 5, 20, 6"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xdeadbeef
        initial_regs[3] = 0x12345678
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_rlwnm(self):
        lst = ["rlwnm 3, 1, 2, 20, 6"]
        initial_regs = [0] * 32
        initial_regs[1] = random.randint(0, (1 << 64)-1)
        initial_regs[2] = random.randint(0, 63)
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_rldicl(self):
        lst = ["rldicl 3, 1, 5, 20"]
        initial_regs = [0] * 32
        initial_regs[1] = random.randint(0, (1 << 64)-1)
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_rldicr(self):
        lst = ["rldicr 3, 1, 5, 20"]
        initial_regs = [0] * 32
        initial_regs[1] = random.randint(0, (1 << 64)-1)
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_regression_extswsli(self):
        lst = [f"extswsli 3, 1, 34"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x5678
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_regression_extswsli_2(self):
        lst = [f"extswsli 3, 1, 7"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3ffffd7377f19fdd
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_regression_extswsli_3(self):
        lst = [f"extswsli 3, 1, 0"]
        initial_regs = [0] * 32
        #initial_regs[1] = 0x80000000fb4013e2
        #initial_regs[1] = 0xffffffffffffffff
        #initial_regs[1] = 0x00000000ffffffff
        initial_regs[1] = 0x0000010180122900
        #initial_regs[1] = 0x3ffffd73f7f19fdd
        self.add_case(Program(lst, bigendian), initial_regs)

    def cse_extswsli(self):
        for i in range(40):
            sh = random.randint(0, 63)
            lst = [f"extswsli 3, 1, {sh}"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def cse_rlc(self):
        insns = ["rldic", "rldicl", "rldicr"]
        for i in range(20):
            choice = random.choice(insns)
            sh = random.randint(0, 63)
            m = random.randint(0, 63)
            lst = [f"{choice} 3, 1, {sh}, {m}"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def cse_ilang(self):
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

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = ShiftRotPipeSpec(id_wid=2)
        m.submodules.alu = alu = ShiftRotBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
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
        print(dir(sim))
        if cxxsim:
            sim.run()
        else:
            with sim.write_vcd("shift_rot_simulator.vcd"):
                sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code):

        rc = yield dec2.e.do.rc.data
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

    runner = unittest.TextTestRunner()
    runner.run(suite)
