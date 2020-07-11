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
from soc.config.endian import bigendian

from soc.fu.test.common import (TestCase, ALUHelpers)
from soc.fu.div.pipeline import DIVBasePipe
from soc.fu.div.pipe_data import DIVPipeSpec
import random

def log_rand(n, min_val=1):
    logrange = random.randint(1, n)
    return random.randint(min_val, (1<<logrange)-1)

def get_cu_inputs(dec2, sim):
    """naming (res) must conform to DIVFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2) # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2) # RB
    yield from ALUHelpers.get_sim_xer_so(res, sim, dec2) # XER.so

    print ("alu get_cu_inputs", res)

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

# Now, instead of doing that, every test case in DIVTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class DIVTestCase(FHDLTestCase):
    test_data = []

    def __init__(self, name):
        super().__init__(name)
        self.test_name = name

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None):
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs)
        self.test_data.append(tc)

    def tst_0_regression(self):
        for i in range(40):
            lst = ["divwo 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = 0xbc716835f32ac00c
            initial_regs[2] = 0xcdf69a7f7042db66
            self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_1_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x10000000000000000-4
        initial_regs[2] = 0x10000000000000000-2
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_2_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffff9321
        initial_regs[2] = 0xffffffffffff7012
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_3_regression(self):
        lst = ["divwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1b8e32f2458746af
        initial_regs[2] = 0x6b8aee2ccf7d62e9
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_4_regression(self):
        lst = ["divw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_5_regression(self):
        lst = ["divw 3, 1, 2",
               "divwo. 6, 4, 5"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        initial_regs[4] = 0x1b8e32f2458746af
        initial_regs[5] = 0x6b8aee2ccf7d62e9
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_6_regression(self):
        # CR0 not getting set properly for this one
        # turns out that overflow is not set correctly in
        # fu/div/output_stage.py calc_overflow
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x61c1cc3b80f2a6af
        initial_regs[2] = 0x9dc66a7622c32bc0
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def test_7_regression(self):
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xf1791627e05e8096
        initial_regs[2] = 0xffc868bf4573da0b
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_divw_by_zero_1(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0x0
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_divw_overflow2(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffffffffffff # top bits don't seem to matter
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_divw_overflow3(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffff
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_rand_divw(self):
        insns = ["divw", "divw.", "divwo", "divwo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_divwuo_regression_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7591a398c4e32b68
        initial_regs[2] = 0x48674ab432867d69
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_divwuo_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x50
        initial_regs[2] = 0x2
        self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_rand_divwu(self):
        insns = ["divwu", "divwu.", "divwuo", "divwuo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            self.run_tst_program(Program(lst, bigendian), initial_regs)

    def tst_ilang(self):
        pspec = DIVPipeSpec(id_wid=2)
        alu = DIVBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("div_pipeline.il", "w") as f:
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

        pspec = DIVPipeSpec(id_wid=2)
        m.submodules.alu = alu = DIVBasePipe(pspec)

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
                        print ("before: so/ov/32", so, ov, ov32)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    fn_unit = yield pdecode2.e.do.fn_unit
                    self.assertEqual(fn_unit, Function.DIV.value)
                    yield from set_alu_inputs(alu, pdecode2, sim)

                    # set valid for one cycle, propagate through pipeline...
                    yield alu.p.valid_i.eq(1)
                    yield
                    yield alu.p.valid_i.eq(0)

                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    vld = yield alu.n.valid_o
                    while not vld:
                        yield
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
                        print ("32bit", hex(is_32bit))
                        print ("signed", hex(is_signed))
                        print ("quotient_root", hex(quotient_root))
                        print ("quotient_65", hex(quotient_65))
                        print ("div_by_zero", hex(div_by_zero))
                        print ("dive_abs_ov32", hex(dive_abs_ov32))
                        print ("quotient_neg", hex(quotient_neg))
                        print ("")
                    yield

                    yield from self.check_alu_outputs(alu, pdecode2, sim, code)
                    yield Settle()

        sim.add_sync_process(process)
        with sim.write_vcd("div_simulator.vcd", "div_simulator.gtkw",
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

        yield from ALUHelpers.get_cr_a(res, alu, dec2)
        yield from ALUHelpers.get_xer_ov(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        print ("res output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        print ("sim output", sim_o)

        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)

        oe = yield dec2.e.do.oe.oe
        oe_ok = yield dec2.e.do.oe.ok
        print ("oe, oe_ok", oe, oe_ok)
        if not oe or not oe_ok:
            # if OE not enabled, XER SO and OV must not be activated
            so_ok = yield alu.n.data_o.xer_so.ok
            ov_ok = yield alu.n.data_o.xer_ov.ok
            print ("so, ov", so_ok, ov_ok)
            self.assertEqual(ov_ok, False, code)
            self.assertEqual(so_ok, False, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(DIVTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
