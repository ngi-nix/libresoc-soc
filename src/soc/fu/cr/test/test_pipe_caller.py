from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmigen.cli import rtlil
import unittest
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_enums import Function
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian

from openpower.test.common import TestAccumulatorBase, ALUHelpers
from openpower.util import mask_extend
from soc.fu.cr.pipeline import CRBasePipe
from soc.fu.cr.pipe_data import CRPipeSpec
import random

from openpower.test.cr.cr_cases import CRTestCase


class CRIlangCase(TestAccumulatorBase):

    def case_ilang(self):
        pspec = CRPipeSpec(id_wid=2)
        alu = CRBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("cr_pipeline.il", "w") as f:
            f.write(vl)


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to CRFunctionUnit input regspec
    """
    res = {}
    full_reg = yield dec2.dec_cr_in.whole_reg.data
    full_reg_ok = yield dec2.dec_cr_in.whole_reg.ok
    full_cr_mask = mask_extend(full_reg, 8, 4)

    # full CR
    print(sim.cr.value)
    if full_reg_ok:
        res['full_cr'] = sim.cr.value & full_cr_mask
    else:
        yield from ALUHelpers.get_sim_cr_a(res, sim, dec2)  # CR A
        yield from ALUHelpers.get_sim_cr_b(res, sim, dec2)  # CR B
        yield from ALUHelpers.get_sim_cr_c(res, sim, dec2)  # CR C

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB

    print("get inputs", res)
    return res


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def set_inputs(self, alu, dec2, simulator):
        inp = yield from get_cu_inputs(dec2, simulator)
        yield from ALUHelpers.set_full_cr(alu, dec2, inp)
        yield from ALUHelpers.set_cr_a(alu, dec2, inp)
        yield from ALUHelpers.set_cr_b(alu, dec2, inp)
        yield from ALUHelpers.set_cr_c(alu, dec2, inp)
        yield from ALUHelpers.set_int_ra(alu, dec2, inp)
        yield from ALUHelpers.set_int_rb(alu, dec2, inp)

    def assert_outputs(self, alu, dec2, simulator, code):
        whole_reg_ok = yield dec2.dec_cr_out.whole_reg.ok
        whole_reg_data = yield dec2.dec_cr_out.whole_reg.data
        full_cr_mask = mask_extend(whole_reg_data, 8, 4)

        cr_en = yield dec2.e.write_cr.ok
        if whole_reg_ok:
            full_cr = yield alu.n.data_o.full_cr.data & full_cr_mask
            expected_cr = simulator.cr.value
            print("CR whole: expected %x, actual: %x mask: %x" % \
                (expected_cr, full_cr, full_cr_mask))
            # HACK: only look at the bits that we expected to change
            self.assertEqual(expected_cr & full_cr_mask, full_cr, code)
        elif cr_en:
            cr_sel = yield dec2.e.write_cr.data
            expected_cr = simulator.cr.value
            print(f"CR whole: {expected_cr:x}, sel {cr_sel}")
            expected_cr = simulator.crl[cr_sel].get_range().value
            real_cr = yield alu.n.data_o.cr.data
            print(f"CR part: expected {expected_cr:x}, actual: {real_cr:x}")
            self.assertEqual(expected_cr, real_cr, code)
        alu_out = yield alu.n.data_o.o.data
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            write_reg_idx = yield dec2.e.write_reg.data
            expected = simulator.gpr(write_reg_idx).value
            print(f"expected {expected:x}, actual: {alu_out:x}")
            self.assertEqual(expected, alu_out, code)

    def execute(self, alu, instruction, pdecode2, test):
        program = test.program
        sim = ISA(pdecode2, test.regs, test.sprs, test.cr, test.mem,
                  test.msr,
                  bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))

        index = sim.pc.CIA.value//4
        while index < len(instructions):
            ins, code = instructions[index]

            print("0x{:X}".format(ins & 0xffffffff))
            print(code)

            # ask the decoder to decode this binary data (endian'd)
            yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()
            yield from self.set_inputs(alu, pdecode2, sim)
            yield alu.p.valid_i.eq(1)
            fn_unit = yield pdecode2.e.do.fn_unit
            self.assertEqual(fn_unit, Function.CR.value, code)
            yield
            opname = code.split(' ')[0]
            yield from sim.call(opname)
            index = sim.pc.CIA.value//4

            vld = yield alu.n.valid_o
            while not vld:
                yield
                vld = yield alu.n.valid_o
            yield
            yield from self.assert_outputs(alu, pdecode2, sim, code)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        fn_name = "CR"
        opkls = CRPipeSpec.opsubsetkls

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(None, opkls, fn_name)
        pdecode = pdecode2.dec

        pspec = CRPipeSpec(id_wid=2)
        m.submodules.alu = alu = CRBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
                print(test.name)
                with self.subTest(test.name):
                    yield from self.execute(alu, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("cr_simulator.vcd"):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(CRTestCase().test_data))
    suite.addTest(TestRunner(CRIlangCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
