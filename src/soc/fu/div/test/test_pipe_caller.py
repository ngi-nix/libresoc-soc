import random
import unittest
from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.cli import rtlil
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import XER_bits, Function
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.config.endian import bigendian

from soc.fu.test.common import (TestCase, ALUHelpers)
from soc.fu.div.pipeline import DivBasePipe
from soc.fu.div.pipe_data import DivPipeSpec, DivPipeKind


def log_rand(n, min_val=1):
    logrange = random.randint(1, n)
    return random.randint(min_val, (1 << logrange)-1)


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to DivFunctionUnit input regspec
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
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)

    yield from ALUHelpers.set_xer_so(alu, dec2, inp)


# This test bench is a bit different than is usual. Initially when I
# was writing it, I had all of the tests call a function to create a
# device under test and simulator, initialize the dut, run the
# simulation for ~2 cycles, and assert that the dut output what it
# should have. However, this was really slow, since it needed to
# create and tear down the dut and simulator for every test case.

# Now, instead of doing that, every test case in DivTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class DivTestCases:
    def __init__(self):
        self.test_data = []
        for n, v in self.__class__.__dict__.items():
            if n.startswith("test") and callable(v):
                self._current_test_name = n
                v(self)

    def run_test_program(self, prog, initial_regs=None, initial_sprs=None):
        tc = TestCase(prog, self._current_test_name,
                      initial_regs, initial_sprs)
        self.test_data.append(tc)

    def tst_0_regression(self):
        for i in range(40):
            lst = ["divwo 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = 0xbc716835f32ac00c
            initial_regs[2] = 0xcdf69a7f7042db66
            self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_1_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x10000000000000000-4
        initial_regs[2] = 0x10000000000000000-2
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_2_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffff9321
        initial_regs[2] = 0xffffffffffff7012
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_3_regression(self):
        lst = ["divwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1b8e32f2458746af
        initial_regs[2] = 0x6b8aee2ccf7d62e9
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_4_regression(self):
        lst = ["divw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_5_regression(self):
        lst = ["divw 3, 1, 2",
               "divwo. 6, 4, 5"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        initial_regs[4] = 0x1b8e32f2458746af
        initial_regs[5] = 0x6b8aee2ccf7d62e9
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_6_regression(self):
        # CR0 not getting set properly for this one
        # turns out that overflow is not set correctly in
        # fu/div/output_stage.py calc_overflow
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x61c1cc3b80f2a6af
        initial_regs[2] = 0x9dc66a7622c32bc0
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_7_regression(self):
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xf1791627e05e8096
        initial_regs[2] = 0xffc868bf4573da0b
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_divw_by_zero_1(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0x0
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_divw_overflow2(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffffffffffff  # top bits don't seem to matter
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_divw_overflow3(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffff
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_divwuo_regression_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7591a398c4e32b68
        initial_regs[2] = 0x48674ab432867d69
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_divwuo_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x50
        initial_regs[2] = 0x2
        self.run_test_program(Program(lst, bigendian), initial_regs)

    def test_all(self):
        instrs = []
        for width in ("w", "d"):
            for sign in ("", "u"):
                for ov in ("", "o"):
                    for cnd in ("", "."):
                        instrs += ["div" + width + sign + ov + cnd,
                                   "div" + width + "e" + sign + ov + cnd]
            for sign in ("s", "u"):
                instrs += ["mod" + sign + width]
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
                        self.run_test_program(prog, initial_regs)

    def tst_rand_divwu(self):
        insns = ["divwu", "divwu.", "divwuo", "divwuo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            self.run_test_program(Program(lst, bigendian), initial_regs)

    def tst_rand_divw(self):
        insns = ["divw", "divw.", "divwo", "divwo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            self.run_test_program(Program(lst, bigendian), initial_regs)


class TestRunner(unittest.TestCase):
    def write_ilang(self, div_pipe_kind):
        pspec = DivPipeSpec(id_wid=2, div_pipe_kind=div_pipe_kind)
        alu = DivBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open(f"div_pipeline_{div_pipe_kind.name}.il", "w") as f:
            f.write(vl)

    def test_write_ilang_div_pipe_core(self):
        self.write_ilang(DivPipeKind.DivPipeCore)

    def test_write_ilang_fsm_div_core(self):
        self.write_ilang(DivPipeKind.FSMDivCore)

    def test_write_ilang_sim_only(self):
        self.write_ilang(DivPipeKind.SimOnly)

    def run_all(self, div_pipe_kind):
        test_data = DivTestCases().test_data
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = DivPipeSpec(id_wid=2, div_pipe_kind=div_pipe_kind)
        m.submodules.alu = alu = DivBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in test_data:
                print(test.name)
                prog = test.program
                with self.subTest(test.name):
                    isa_sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                                  test.mem, test.msr,
                                  bigendian=bigendian)
                    gen = prog.generate_instructions()
                    instructions = list(zip(gen, prog.assembly.splitlines()))
                    yield Delay(0.1e-6)

                    index = isa_sim.pc.CIA.value//4
                    while index < len(instructions):
                        ins, code = instructions[index]

                        print("instruction: 0x{:X}".format(ins & 0xffffffff))
                        print(code)
                        spr = isa_sim.spr
                        if 'XER' in spr:
                            so = 1 if spr['XER'][XER_bits['SO']] else 0
                            ov = 1 if spr['XER'][XER_bits['OV']] else 0
                            ov32 = 1 if spr['XER'][XER_bits['OV32']] else 0
                            print("before: so/ov/32", so, ov, ov32)

                        # ask the decoder to decode this binary data (endian'd)
                        # little / big?
                        yield pdecode2.dec.bigendian.eq(bigendian)
                        yield instruction.eq(ins)          # raw binary instr.
                        yield Delay(0.1e-6)
                        fn_unit = yield pdecode2.e.do.fn_unit
                        self.assertEqual(fn_unit, Function.DIV.value)
                        yield from set_alu_inputs(alu, pdecode2, isa_sim)

                        # set valid for one cycle, propagate through pipeline..
                        # note that it is critically important to do this
                        # for DIV otherwise it starts trying to produce
                        # multiple results.
                        yield alu.p.valid_i.eq(1)
                        yield
                        yield alu.p.valid_i.eq(0)

                        opname = code.split(' ')[0]
                        yield from isa_sim.call(opname)
                        index = isa_sim.pc.CIA.value//4

                        vld = yield alu.n.valid_o
                        while not vld:
                            yield
                            yield Delay(0.1e-6)
                            vld = yield alu.n.valid_o
                            # bug #425 investigation
                            do = alu.pipe_end.div_out
                            ctx_op = do.i.ctx.op
                            is_32bit = yield ctx_op.is_32bit
                            is_signed = yield ctx_op.is_signed
                            quotient_root = yield do.i.core.quotient_root
                            quotient_65 = yield do.quotient_65
                            dive_abs_ov32 = yield do.i.dive_abs_ov32
                            div_by_zero = yield do.i.div_by_zero
                            quotient_neg = yield do.quotient_neg
                            print("32bit", hex(is_32bit))
                            print("signed", hex(is_signed))
                            print("quotient_root", hex(quotient_root))
                            print("quotient_65", hex(quotient_65))
                            print("div_by_zero", hex(div_by_zero))
                            print("dive_abs_ov32", hex(dive_abs_ov32))
                            print("quotient_neg", hex(quotient_neg))
                            print("")
                        yield

                        yield Delay(0.1e-6)
                        # XXX sim._state is an internal variable
                        # and timeline does not exist
                        # AttributeError: '_SimulatorState' object
                        #                 has no attribute 'timeline'
                        # TODO: raise bugreport with whitequark
                        # requesting a public API to access this "officially"
                        # XXX print("time:", sim._state.timeline.now)
                        yield from self.check_alu_outputs(alu, pdecode2,
                                                          isa_sim, code)

        sim.add_sync_process(process)
        with sim.write_vcd(f"div_simulator_{div_pipe_kind.name}.vcd",
                           f"div_simulator_{div_pipe_kind.name}.gtkw",
                           traces=[]):
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
        yield from ALUHelpers.get_xer_ov(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        print("res output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        print("sim output", sim_o)

        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)

        oe = yield dec2.e.do.oe.oe
        oe_ok = yield dec2.e.do.oe.ok
        print("oe, oe_ok", oe, oe_ok)
        if not oe or not oe_ok:
            # if OE not enabled, XER SO and OV must not be activated
            so_ok = yield alu.n.data_o.xer_so.ok
            ov_ok = yield alu.n.data_o.xer_ov.ok
            print("so, ov", so_ok, ov_ok)
            self.assertEqual(ov_ok, False, code)
            self.assertEqual(so_ok, False, code)

    def test_run_div_pipe_core(self):
        self.run_all(DivPipeKind.DivPipeCore)

    def test_run_fsm_div_core(self):
        self.run_all(DivPipeKind.FSMDivCore)

    def test_run_sim_only(self):
        self.run_all(DivPipeKind.SimOnly)


if __name__ == "__main__":
    unittest.main()
