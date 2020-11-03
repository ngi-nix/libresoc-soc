from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

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
#from soc.fu.spr.pipeline import SPRBasePipe
#from soc.fu.spr.pipe_data import SPRPipeSpec
from soc.fu.mmu.fsm import FSMMMUStage
from soc.fu.mmu.pipe_data import MMUPipeSpec
import random

from soc.fu.div.test.helper import (log_rand, get_cu_inputs,
                                    set_alu_inputs, DivTestHelper)

def set_fsm_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    print("Error here")
    inp = yield from get_cu_inputs(dec2, sim)
    # set int registers a and b
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)
    # TODO set spr register
    # yield from ALUHelpers.set_spr_spr1(alu, dec2, inp)


def check_fsm_outputs(fsm, pdecode2, sim, code):
    # check that MMUOutputData is correct
    return None #TODO

#incomplete test - connect fsm inputs first
class MMUTestCase(TestAccumulatorBase): 

    def case_1_mmu(self):
        # test case for MTSPR, MFSPR, DCBZ and TLBIE.
        lst = [#"dcbz 1, 1",
               "mfspr 1, 26",  # SRR0
               "mfspr 2, 27",  # SRR1
               "mfspr 3, 8",  # LR
               "mfspr 4, 1", ]  # XER
        initial_regs = [0] * 32
        initial_sprs = {'SRR0': 0x12345678, 'SRR1': 0x5678, 'LR': 0x1234,
                        'XER': 0xe00c0000}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    #def case_ilang(self):
    #    pspec = SPRPipeSpec(id_wid=2)
    #    alu = SPRBasePipe(pspec)
    #    vl = rtlil.convert(alu, ports=alu.ports())
    #    with open("trap_pipeline.il", "w") as f:
    #        f.write(vl)


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def execute(self, fsm, instruction, pdecode2, test):
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
            fsm_o_unused = yield from set_fsm_inputs(fsm, pdecode2, sim)
            yield
            opname = code.split(' ')[0]
            yield from sim.call(opname)
            pc = sim.pc.CIA.value
            msr = sim.msr.value
            index = pc//4
            print("pc after %08x" % (pc))

            vld = yield fsm.n.valid_o #fsm
            while not vld:
                yield
                print("not valid -- hang")
                vld = yield fsm.n.valid_o
            yield

            #yield from self.check_fsm_outputs(fsm, pdecode2, sim, code)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = MMUPipeSpec(id_wid=2)
        m.submodules.fsm = fsm = FSMMMUStage(pspec)

        #FIXME connect fsm inputs

        comb += fsm.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += fsm.p.valid_i.eq(1)
        comb += fsm.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
                print("test", test.name)
                print("sprs", test.sprs)
                program = test.program
                with self.subTest(test.name):
                    yield from self.execute(fsm, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("alu_simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()

if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(MMUTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
