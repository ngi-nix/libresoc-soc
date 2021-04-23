import random
from soc.fu.alu.pipe_data import ALUPipeSpec
from soc.fu.alu.pipeline import ALUBasePipe
from openpower.test.common import (TestAccumulatorBase, ALUHelpers)
from openpower.endian import bigendian
from openpower.decoder.isa.all import ISA
from openpower.decoder.power_enums import (XER_bits, Function)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.isa.caller import special_sprs
import unittest
from nmigen.cli import rtlil
from nmutil.formaltest import FHDLTestCase
from nmigen import Module, Signal

from openpower.test.alu.alu_cases import ALUTestCase

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to ALUFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
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

    yield from ALUHelpers.set_xer_ca(alu, dec2, inp)
    yield from ALUHelpers.set_xer_so(alu, dec2, inp)


class ALUIAllCases(ALUTestCase):

    def case_ilang(self):
        pspec = ALUPipeSpec(id_wid=2)
        alu = ALUBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("alu_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(unittest.TestCase):

    def execute(self, alu,instruction, pdecode2, test):
        program = test.program
        sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                  test.mem, test.msr,
                  bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))

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
            # little / big?
            yield pdecode2.dec.bigendian.eq(bigendian)
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()
            fn_unit = yield pdecode2.e.do.fn_unit
            asmcode = yield pdecode2.e.asmcode
            dec_asmcode = yield pdecode2.dec.op.asmcode
            print ("asmcode", asmcode, dec_asmcode)
            self.assertEqual(fn_unit, Function.ALU.value)
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
            yield

            yield from self.check_alu_outputs(alu, pdecode2, sim, code)
            yield Settle()

    def test_it(self):
        test_data = ALUTestCase().test_data
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        fn_name = "ALU"
        opkls = ALUPipeSpec.opsubsetkls

        pdecode = create_pdecode()
        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode, opkls, fn_name)
        pdecode = pdecode2.dec

        pspec = ALUPipeSpec(id_wid=2)
        m.submodules.alu = alu = ALUBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in test_data:
                print(test.name)
                program = test.program
                with self.subTest(test.name):
                    yield from self.execute(alu, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("alu_simulator.vcd"):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code):

        rc = yield dec2.e.do.rc.rc
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
        yield from ALUHelpers.get_xer_ca(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ca(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_ca(self, res, sim_o, code)
        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main()
