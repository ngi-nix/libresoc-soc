from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmigen.cli import rtlil
import unittest
from openpower.decoder.power_decoder import create_pdecode
from openpower.decoder.power_decoder2 import PowerDecode2
from openpower.decoder.power_enums import (XER_bits, Function, MicrOp, CryIn)
from openpower.simulator.program import Program
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian
from openpower.consts import MSR

from openpower.test.mmu.mmu_cases import MMUTestCase

from openpower.test.common import (TestAccumulatorBase, skip_case, ALUHelpers)
from soc.config.test.test_loadstore import TestMemPspec
#from soc.fu.spr.pipeline import SPRBasePipe
#from soc.fu.spr.pipe_data import SPRPipeSpec
from soc.fu.mmu.fsm import FSMMMUStage, LoadStore1
from soc.fu.mmu.pipe_data import MMUPipeSpec
import random

from soc.fu.div.test.helper import (log_rand, get_cu_inputs,
                                    set_alu_inputs)

import power_instruction_analyzer as pia

debughang = 1

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

    overflow = None
    a=None
    b=None
    # TODO
    if 'xer_so' in inp:
        print("xer_so::::::::::::::::::::::::::::::::::::::::::::::::")
        so = inp['xer_so']
        print(so)
        overflow = pia.OverflowFlags(so=bool(so),
                                      ov=False,
                                      ov32=False)
    if 'ra' in inp:
        a = inp['ra']
    if 'rb' in inp:
        b = inp['rb']
    print(inp)
    return pia.InstructionInput(ra=a, rb=b, overflow=overflow)


def check_fsm_outputs(fsm, pdecode2, sim, code):
    # check that MMUOutputData is correct
    return None #TODO

#incomplete test - connect fsm inputs first
class MMUIlangCase(TestAccumulatorBase):
    #def case_ilang(self):
    #    pspec = SPRPipeSpec(id_wid=2)
    #    alu = SPRBasePipe(pspec)
    #    vl = rtlil.convert(alu, ports=alu.ports())
    #    with open("trap_pipeline.il", "w") as f:
    #        f.write(vl)
    pass


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def check_fsm_outputs(self, alu, dec2, sim, code, pia_res):

        rc = yield dec2.e.do.rc.data
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print("check extra output", repr(code), cridx_ok, cridx)
        if rc:
            self.assertEqual(cridx, 0, code)

        sim_o = {}
        res = {}

        #MMUOutputData does not have xer

        yield from ALUHelpers.get_cr_a(res, alu, dec2)
        #yield from ALUHelpers.get_xer_ov(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        #yield from ALUHelpers.get_xer_so(res, alu, dec2)


        print("res output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        #yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        #yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        print("sim output", sim_o)

        print("power-instruction-analyzer result:")
        print(pia_res)
        #if pia_res is not None:
        #    with self.subTest(check="pia", sim_o=sim_o, pia_res=str(pia_res)):
        #        pia_o = pia_res_to_output(pia_res)
        #        ALUHelpers.check_int_o(self, res, pia_o, code)
        #        ALUHelpers.check_cr_a(self, res, pia_o, code)
        #        #ALUHelpers.check_xer_ov(self, res, pia_o, code)
        #        #ALUHelpers.check_xer_so(self, res, pia_o, code)

        with self.subTest(check="sim", sim_o=sim_o, pia_res=str(pia_res)):
            #ALUHelpers.check_int_o(self, res, sim_o, code) # mmu is not an alu
            ALUHelpers.check_cr_a(self, res, sim_o, code)
            #ALUHelpers.check_xer_ov(self, res, sim_o, code)
            #ALUHelpers.check_xer_so(self, res, sim_o, code)

        #oe = yield dec2.e.do.oe.oe
        #oe_ok = yield dec2.e.do.oe.ok
        #print("oe, oe_ok", oe, oe_ok)
        #if not oe or not oe_ok:
        #    # if OE not enabled, XER SO and OV must not be activated
        #    so_ok = yield alu.n.data_o.xer_so.ok
        #    ov_ok = yield alu.n.data_o.xer_ov.ok
        #    print("so, ov", so_ok, ov_ok)
        #    self.assertEqual(ov_ok, False, code)
        #    self.assertEqual(so_ok, False, code)

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
            #FIXME this fails -- self.assertEqual(fn_unit, Function.SPR.value)
            pia_res = yield from set_fsm_inputs(fsm, pdecode2, sim)
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
                if debughang:
                    print("not valid -- hang")
                    return
                vld = yield fsm.n.valid_o
                if debughang==2: vld=1
            yield

            yield from self.check_fsm_outputs(fsm, pdecode2, sim, code, pia_res)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pspec = TestMemPspec(addr_wid=48,
                             mask_wid=8,
                             reg_wid=64,
                             )

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pipe_spec = MMUPipeSpec(id_wid=2)
        ldst = LoadStore1(pspec)
        fsm = FSMMMUStage(pipe_spec)
        fsm.set_ldst_interface(ldst)
        m.submodules.fsm = fsm
        m.submodules.ldst = ldst

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
    suite.addTest(TestRunner(MMUIlangCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
