"""trap pipeline tests

issues:
* https://bugs.libre-soc.org/show_bug.cgi?id=629
"""

from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmigen.cli import rtlil
import unittest
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_enums import XER_bits, Function
from openpower.decoder.selectable_int import SelectableInt
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian
from openpower.consts import MSR

from openpower.test.common import TestAccumulatorBase, ALUHelpers
from soc.fu.trap.pipeline import TrapBasePipe
from soc.fu.trap.pipe_data import TrapPipeSpec
import random

from openpower.test.trap.trap_cases import TrapTestCase


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to TrapFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
    yield from ALUHelpers.get_sim_fast_spr1(res, sim, dec2)  # SPR0
    yield from ALUHelpers.get_sim_fast_spr2(res, sim, dec2)  # SPR1
    yield from ALUHelpers.get_sim_fast_spr3(res, sim, dec2)  # SVSRR0
    ALUHelpers.get_sim_cia(res, sim, dec2)  # PC
    ALUHelpers.get_sim_msr(res, sim, dec2)  # MSR

    print("alu get_cu_inputs", res)

    return res


def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)
    yield from ALUHelpers.set_fast_spr1(alu, dec2, inp)  # SPR0
    yield from ALUHelpers.set_fast_spr2(alu, dec2, inp)  # SPR1
    yield from ALUHelpers.set_fast_spr3(alu, dec2, inp)  # SVSRR0

    # yield from ALUHelpers.set_cia(alu, dec2, inp)
    # yield from ALUHelpers.set_msr(alu, dec2, inp)
    return inp


class TrapIlangCase(TestAccumulatorBase):

    def case_ilang(self):
        pspec = TrapPipeSpec(id_wid=2)
        alu = TrapBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("trap_pipeline.il", "w") as f:
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

        pspec = TrapPipeSpec(id_wid=2)
        m.submodules.alu = alu = TrapBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += alu.p.valid_i.eq(1)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
                print(test.name)
                program = test.program
                with self.subTest(test.name):
                    sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                              test.mem, test.msr,
                              bigendian=bigendian)
                    gen = program.generate_instructions()
                    instructions = list(zip(gen, program.assembly.splitlines()))

                    msr = sim.msr.value
                    pc = sim.pc.CIA.value
                    print("starting msr, pc %08x, %08x" % (msr, pc))
                    index = pc//4
                    while index < len(instructions):
                        ins, code = instructions[index]

                        print("pc %08x msr %08x instr: %08x" % (pc, msr, ins))
                        print(code)
                        if 'XER' in sim.spr:
                            so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                            ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                            ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                            print("before: so/ov/32", so, ov, ov32)

                        # ask the decoder to decode this binary data (endian'd)
                        yield pdecode2.dec.bigendian.eq(bigendian)  # l/big?
                        yield pdecode2.state.msr.eq(msr)  # set MSR in pdecode2
                        yield pdecode2.state.pc.eq(pc)  # set CIA in pdecode2
                        yield instruction.eq(ins)          # raw binary instr.
                        yield Settle()
                        fn_unit = yield pdecode2.e.do.fn_unit
                        self.assertEqual(fn_unit, Function.TRAP.value)
                        alu_o = yield from set_alu_inputs(alu, pdecode2, sim)
                        yield
                        opname = code.split(' ')[0]
                        yield from sim.call(opname)
                        pc = sim.pc.CIA.value
                        index = pc//4
                        print("pc after %08x" % (pc))
                        msr = sim.msr.value
                        print("msr after %08x" % (msr))

                        vld = yield alu.n.valid_o
                        while not vld:
                            yield
                            vld = yield alu.n.valid_o
                        yield

                        yield from self.check_alu_outputs(alu, pdecode2,
                                                          sim, code)

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
        yield from ALUHelpers.get_fast_spr2(res, alu, dec2)
        yield from ALUHelpers.get_fast_spr3(res, alu, dec2)
        yield from ALUHelpers.get_nia(res, alu, dec2)
        yield from ALUHelpers.get_msr(res, alu, dec2)

        print("output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr1(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr2(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr3(sim_o, sim, dec2)
        ALUHelpers.get_sim_nia(sim_o, sim, dec2)
        ALUHelpers.get_sim_msr(sim_o, sim, dec2)

        print("sim output", sim_o)

        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_fast_spr1(self, res, sim_o, code)
        ALUHelpers.check_fast_spr2(self, res, sim_o, code)
        ALUHelpers.check_fast_spr3(self, res, sim_o, code)
        ALUHelpers.check_nia(self, res, sim_o, code)
        ALUHelpers.check_msr(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(TrapTestCase().test_data))
    suite.addTest(TestRunner(TrapIlangCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
