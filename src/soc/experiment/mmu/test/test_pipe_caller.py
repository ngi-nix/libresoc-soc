from nmigen import Module, Signal
from nmigen.sim.pysim import Simulator, Delay, Settle
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, MicrOp, CryIn)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.config.endian import bigendian

from soc.fu.test.common import (TestAccumulatorBase, TestCase, ALUHelpers)
from soc.fu.mul.pipeline import MulBasePipe
from soc.fu.mul.pipe_data import MulPipeSpec
import random


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to MulFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
    yield from ALUHelpers.get_sim_xer_so(res, sim, dec2)  # XER.so

    print("alu get_cu_inputs", res)

    return res


def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    print("set alu inputs", inp)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)

    yield from ALUHelpers.set_xer_so(alu, dec2, inp)


# This test bench is a bit different than is usual. Initially when I
# was writing it, I had all of the tests call a function to create a
# device under test and simulator, initialize the dut, run the
# simulation for ~2 cycles, and assert that the dut output what it
# should have. However, this was really slow, since it needed to
# create and tear down the dut and simulator for every test case.

# Now, instead of doing that, every test case in MulTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class MulTestCase(TestAccumulatorBase):

    def case_0_mullw(self):
        lst = [f"mullw 3, 1, 2"]
        initial_regs = [0] * 32
        #initial_regs[1] = 0xffffffffffffffff
        #initial_regs[2] = 0xffffffffffffffff
        initial_regs[1] = 0x2ffffffff
        initial_regs[2] = 0x2
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_1_mullwo_(self):
        lst = [f"mullwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3b34b06f
        initial_regs[2] = 0xfdeba998
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_2_mullwo(self):
        lst = [f"mullwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffffa988  # -5678
        initial_regs[2] = 0xffffffffffffedcc  # -1234
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_3_mullw(self):
        lst = ["mullw 3, 1, 2",
               "mullw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x6
        initial_regs[2] = 0xe
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_4_mullw_rand(self):
        for i in range(40):
            lst = ["mullw 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_4_mullw_nonrand(self):
        for i in range(40):
            lst = ["mullw 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = i+1
            initial_regs[2] = i+20
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_mulhw__regression_1(self):
        lst = ["mulhw. 3, 1, 2"
               ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7745b36eca6646fa
        initial_regs[2] = 0x47dfba3a63834ba2
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mul_lh(self):
        insns = ["mulhw", "mulhw.", "mulhwu", "mulhwu."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mullw(self):
        insns = ["mullw", "mullw.", "mullwo", "mullwo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mulld(self):
        insns = ["mulld", "mulld.", "mulldo", "mulldo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mulhd(self):
        insns = ["mulhd", "mulhd."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_all(self):
        instrs = ["mulhw",
                  "mulhw.", "mullw",
                  "mullw.", "mullwo",
                  "mullwo.", "mulhwu",
                  "mulhwu.", "mulld",
                  "mulld.", "mulldo",
                  "mulldo.", "mulhd",
                  "mulhd.", "mulhdu",
                  "mulhdu."]

        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for instr in instrs:
            l = [f"{instr} 3, 1, 2"]
            for ra in test_values:
                for rb in test_values:
                    initial_regs = [0] * 32
                    initial_regs[1] = ra
                    initial_regs[2] = rb
                    # use "with" so as to close the files used
                    with Program(l, bigendian) as prog:
                        self.add_case(prog, initial_regs)

    def case_all_rb_randint(self):
        instrs = ["mulhw",
                  "mulhw.", "mullw",
                  "mullw.", "mullwo",
                  "mullwo.", "mulhwu",
                  "mulhwu.", "mulld",
                  "mulld.", "mulldo",
                  "mulldo.", "mulhd",
                  "mulhd.", "mulhdu",
                  "mulhdu."]

        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for instr in instrs:
            l = [f"{instr} 3, 1, 2"]
            for ra in test_values:
                initial_regs = [0] * 32
                initial_regs[1] = ra
                initial_regs[2] = random.randint(0, (1 << 64)-1)
                # use "with" so as to close the files used
                with Program(l, bigendian) as prog:
                    self.add_case(prog, initial_regs)

    def case_all_rb_close_to_ov(self):
        instrs = ["mulhw",
                  "mulhw.", "mullw",
                  "mullw.", "mullwo",
                  "mullwo.", "mulhwu",
                  "mulhwu.", "mulld",
                  "mulld.", "mulldo",
                  "mulldo.", "mulhd",
                  "mulhd.", "mulhdu",
                  "mulhdu."]

        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for instr in instrs:
            for i in range(20):
                x = 0x7fffffff + random.randint(0, 1)
                ra = random.randint(0, (1 << 32)-1)
                rb = x // ra

                l = [f"{instr} 3, 1, 2"]
                initial_regs = [0] * 32
                initial_regs[1] = ra
                initial_regs[2] = rb
                # use "with" so as to close the files used
                with Program(l, bigendian) as prog:
                    self.add_case(prog, initial_regs)

    def case_mulli(self):

        imm_values = [-32768, -32767, -32766, -2, -1, 0, 1, 2, 32766, 32767]

        ra_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for i in range(20):
            imm_values.append(random.randint(-1 << 15, (1 << 15) - 1))

        for i in range(14):
            ra_values.append(random.randint(0, (1 << 64) - 1))

        for ra in ra_values:
            for imm in imm_values:
                l = [f"mulli 0, 1, {imm}"]
                initial_regs = [0] * 32
                initial_regs[1] = ra
                # use "with" so as to close the files used
                with Program(l, bigendian) as prog:
                    self.add_case(prog, initial_regs)

# TODO add test case for these 3 operand cases (madd
# needs to be implemented)
# "maddhd","maddhdu","maddld"

    def case_ilang(self):
        pspec = MulPipeSpec(id_wid=2)
        alu = MulBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("mul_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = MulPipeSpec(id_wid=2)
        m.submodules.alu = alu = MulBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
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
                          test.mem, test.msr,
                          bigendian=bigendian)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))
                yield Settle()

                index = sim.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("instruction: 0x{:X}".format(ins & 0xffffffff))
                    print(code)
                    if 'XER' in sim.spr:
                        so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                        ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                        ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                        print("before: so/ov/32", so, ov, ov32)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    fn_unit = yield pdecode2.e.do.fn_unit
                    self.assertEqual(fn_unit, Function.MUL.value)
                    yield from set_alu_inputs(alu, pdecode2, sim)

                    # set valid for one cycle, propagate through pipeline...
                    yield alu.p.valid_i.eq(1)
                    yield
                    yield alu.p.valid_i.eq(0)

                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    # ...wait for valid to pop out the end
                    vld = yield alu.n.valid_o
                    while not vld:
                        yield
                        vld = yield alu.n.valid_o
                    yield

                    yield from self.check_alu_outputs(alu, pdecode2, sim, code)
                    yield Settle()

        sim.add_sync_process(process)
        with sim.write_vcd("mul_simulator.vcd", "mul_simulator.gtkw",
                           traces=[]):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code):

        rc = yield dec2.e.do.rc.data
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print("check extra output", repr(code), cridx_ok, cridx)
        if rc:
            self.assertEqual(cridx, 0, code)

        oe = yield dec2.e.do.oe.oe
        oe_ok = yield dec2.e.do.oe.ok
        if not oe or not oe_ok:
            # if OE not enabled, XER SO and OV must correspondingly be false
            so_ok = yield alu.n.data_o.xer_so.ok
            ov_ok = yield alu.n.data_o.xer_ov.ok
            self.assertEqual(so_ok, False, code)
            self.assertEqual(ov_ok, False, code)

        sim_o = {}
        res = {}

        yield from ALUHelpers.get_cr_a(res, alu, dec2)
        yield from ALUHelpers.get_xer_ov(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)
        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(MulTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
