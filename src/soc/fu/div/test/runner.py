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

from soc.fu.test.common import ALUHelpers
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


class DivRunner(unittest.TestCase):
    def __init__(self, test_data, div_pipe_kind=None):
        print ("DivRunner", test_data, div_pipe_kind)
        super().__init__("run_all")
        self.test_data = test_data
        self.div_pipe_kind = div_pipe_kind

    def write_ilang(self):
        pspec = DivPipeSpec(id_wid=2, div_pipe_kind=self.div_pipe_kind)
        alu = DivBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open(f"div_pipeline_{div_pipe_kind.name}.il", "w") as f:
            f.write(vl)

    def test_write_ilang(self):
        self.write_ilang(self.div_pipe_kind)

    def run_all(self):
        # *sigh* this is a mess.  unit test gets added by code-walking
        # (unittest module) and picked up with a test name.
        # we don't want that: we want it explicitly called
        # (see div test_pipe_caller.py) - don't know what to do,
        # so "fix" it by adding default param and returning here
        if self.div_pipe_kind is None:
            return

        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = DivPipeSpec(id_wid=2, div_pipe_kind=self.div_pipe_kind)
        m.submodules.alu = alu = DivBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
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
        with sim.write_vcd(f"div_simulator_{self.div_pipe_kind.name}.vcd"):
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

