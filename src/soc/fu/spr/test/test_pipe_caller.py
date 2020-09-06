from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
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
from soc.consts import MSR


from soc.fu.test.common import (
    TestAccumulatorBase, skip_case, TestCase, ALUHelpers)
from soc.fu.spr.pipeline import SPRBasePipe
from soc.fu.spr.pipe_data import SPRPipeSpec
import random


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to SPRFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
    yield from ALUHelpers.get_sim_slow_spr1(res, sim, dec2)  # FAST1
    yield from ALUHelpers.get_sim_fast_spr1(res, sim, dec2)  # FAST1
    yield from ALUHelpers.get_rd_sim_xer_ca(res, sim, dec2)  # XER.ca
    yield from ALUHelpers.get_sim_xer_ov(res, sim, dec2)  # XER.ov
    yield from ALUHelpers.get_sim_xer_so(res, sim, dec2)  # XER.so

    print("spr get_cu_inputs", res)

    return res


def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_xer_ca(alu, dec2, inp)
    yield from ALUHelpers.set_xer_ov(alu, dec2, inp)
    yield from ALUHelpers.set_xer_so(alu, dec2, inp)

    yield from ALUHelpers.set_fast_spr1(alu, dec2, inp)
    yield from ALUHelpers.set_slow_spr1(alu, dec2, inp)
    return inp


# This test bench is a bit different than is usual. Initially when I
# was writing it, I had all of the tests call a function to create a
# device under test and simulator, initialize the dut, run the
# simulation for ~2 cycles, and assert that the dut output what it
# should have. However, this was really slow, since it needed to
# create and tear down the dut and simulator for every test case.

# Now, instead of doing that, every test case in SPRTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class SPRTestCase(TestAccumulatorBase):

    def case_1_mfspr(self):
        lst = ["mfspr 1, 26",  # SRR0
               "mfspr 2, 27",  # SRR1
               "mfspr 3, 8",  # LR
               "mfspr 4, 1", ]  # XER
        initial_regs = [0] * 32
        initial_sprs = {'SRR0': 0x12345678, 'SRR1': 0x5678, 'LR': 0x1234,
                        'XER': 0xe00c0000}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    def case_1_mtspr(self):
        lst = ["mtspr 26, 1",  # SRR0
               "mtspr 27, 2",  # SRR1
               "mtspr 1, 3",  # XER
               "mtspr 9, 4", ]  # CTR
        initial_regs = [0] * 32
        initial_regs[1] = 0x129518230011feed
        initial_regs[2] = 0x123518230011feed
        initial_regs[3] = 0xe00c0000
        initial_regs[4] = 0x1010101010101010
        initial_sprs = {'SRR0': 0x12345678, 'SRR1': 0x5678, 'LR': 0x1234,
                        'XER': 0x0}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    def case_2_mtspr_mfspr(self):
        lst = ["mtspr 26, 1",  # SRR0
               "mtspr 27, 2",  # SRR1
               "mtspr 1, 3",  # XER
               "mtspr 9, 4",  # CTR
               "mfspr 2, 26",  # SRR0
               "mfspr 3, 27",  # and into reg 2
               "mfspr 4, 1",  # XER
               "mfspr 5, 9", ]  # CTR
        initial_regs = [0] * 32
        initial_regs[1] = 0x129518230011feed
        initial_regs[2] = 0x123518230011feed
        initial_regs[3] = 0xe00c0000
        initial_regs[4] = 0x1010101010101010
        initial_sprs = {'SRR0': 0x12345678, 'SRR1': 0x5678, 'LR': 0x1234,
                        'XER': 0x0}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    # TODO XXX whoops...
    @skip_case("spr does not have TRAP in it. has to be done another way")
    def case_3_mtspr_priv(self):
        lst = ["mtspr 26, 1",  # SRR0
               "mtspr 27, 2",  # SRR1
               "mtspr 1, 3",  # XER
               "mtspr 9, 4", ]  # CTR
        initial_regs = [0] * 32
        initial_regs[1] = 0x129518230011feed
        initial_regs[2] = 0x123518230011feed
        initial_regs[3] = 0xe00c0000
        initial_regs[4] = 0x1010101010101010
        initial_sprs = {'SRR0': 0x12345678, 'SRR1': 0x5678, 'LR': 0x1234,
                        'XER': 0x0}
        msr = 1 << MSR.PR
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs, initial_msr=msr)

    def case_4_mfspr_slow(self):
        lst = ["mfspr 1, 272",    # SPRG0
               "mfspr 4, 273", ]  # SPRG1
        initial_regs = [0] * 32
        initial_sprs = {'SPRG0_priv': 0x12345678, 'SPRG1_priv': 0x5678,
                        }
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    def case_5_mtspr(self):
        lst = ["mtspr 272, 1",  # SPRG0
               "mtspr 273, 2",  # SPRG1
               ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x129518230011feed
        initial_regs[2] = 0x123518230011fee0
        initial_sprs = {'SPRG0_priv': 0x12345678, 'SPRG1_priv': 0x5678,
                        }
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    def case_ilang(self):
        pspec = SPRPipeSpec(id_wid=2)
        alu = SPRBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("trap_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def execute(self, alu, instruction, pdecode2, test):
        program = test.program
        sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                  test.mem, test.msr,
                  bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))

        pc = sim.pc.CIA.value
        msr = sim.msr.value
        index = pc//4
        while index < len(instructions):
            ins, code = instructions[index]

            print("pc %08x instr: %08x" % (pc, ins & 0xffffffff))
            print(code)

            if 'XER' in sim.spr:
                so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                print("before: so/ov/32", so, ov, ov32)

            # ask the decoder to decode this binary data (endian'd)
            yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
            yield pdecode2.state.msr.eq(msr)  # set MSR in pdecode2
            yield pdecode2.state.pc.eq(pc)  # set PC in pdecode2
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()

            fast_in = yield pdecode2.e.read_fast1.data
            spr_in = yield pdecode2.e.read_spr1.data
            print("dec2 spr/fast in", fast_in, spr_in)

            fast_out = yield pdecode2.e.write_fast1.data
            spr_out = yield pdecode2.e.write_spr.data
            print("dec2 spr/fast in", fast_out, spr_out)

            fn_unit = yield pdecode2.e.do.fn_unit
            self.assertEqual(fn_unit, Function.SPR.value)
            alu_o = yield from set_alu_inputs(alu, pdecode2, sim)
            yield
            opname = code.split(' ')[0]
            yield from sim.call(opname)
            pc = sim.pc.CIA.value
            msr = sim.msr.value
            index = pc//4
            print("pc after %08x" % (pc))

            vld = yield alu.n.valid_o
            while not vld:
                yield
                vld = yield alu.n.valid_o
            yield

            yield from self.check_alu_outputs(alu, pdecode2, sim, code)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = SPRPipeSpec(id_wid=2)
        m.submodules.alu = alu = SPRBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.p.valid_i.eq(1)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
                print("test", test.name)
                print("sprs", test.sprs)
                program = test.program
                with self.subTest(test.name):
                    yield from self.execute(alu, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("alu_simulator.vcd", "simulator.gtkw",
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

        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_fast_spr1(res, alu, dec2)
        yield from ALUHelpers.get_slow_spr1(res, alu, dec2)
        yield from ALUHelpers.get_xer_ov(res, alu, dec2)
        yield from ALUHelpers.get_xer_ca(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        print("output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_xer_so(sim_o, sim, alu, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ov(sim_o, sim, alu, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ca(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr1(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_slow_spr1(sim_o, sim, dec2)

        print("sim output", sim_o)

        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_ca(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)
        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_fast_spr1(self, res, sim_o, code)
        ALUHelpers.check_slow_spr1(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(SPRTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
