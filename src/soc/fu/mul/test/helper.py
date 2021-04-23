from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Delay, Settle

import power_instruction_analyzer as pia

from nmigen.cli import rtlil
import unittest
from openpower.decoder.isa.caller import ISACaller, special_sprs
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_enums import (XER_bits, Function, MicrOp, CryIn)
from openpower.decoder.selectable_int import SelectableInt
from openpower.simulator.program import Program
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian

from openpower.test.common import (TestAccumulatorBase, TestCase, ALUHelpers)
from soc.fu.test.pia import pia_res_to_output
from soc.fu.mul.pipeline import MulBasePipe
from soc.fu.mul.pipe_data import MulPipeSpec
import random


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to MulFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
    yield from ALUHelpers.get_sim_int_rc(res, sim, dec2)  # RC
    yield from ALUHelpers.get_sim_xer_so(res, sim, dec2)  # XER.so

    print("alu get_cu_inputs", res)

    return res


def set_alu_inputs(alu, dec2, sim, has_third_input):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    print("set alu inputs", inp)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)
    if has_third_input:
        yield from ALUHelpers.set_int_rc(alu, dec2, inp)

    yield from ALUHelpers.set_xer_so(alu, dec2, inp)

    overflow = None
    if 'xer_so' in inp:
        so = inp['xer_so']
        overflow = pia.OverflowFlags(so=bool(so),
                                     ov=False,
                                     ov32=False)
    rc = inp["rc"] if has_third_input else None
    return pia.InstructionInput(ra=inp.get("ra"), rb=inp.get("rb"),
                                rc=rc, overflow=overflow)


class MulTestHelper(unittest.TestCase):
    def execute(self, pdecode2, test, instruction, alu, has_third_input, sim):
        program = test.program
        isa_sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                      test.mem, test.msr,
                      bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))
        yield Settle()

        index = isa_sim.pc.CIA.value//4
        while index < len(instructions):
            ins, code = instructions[index]

            print("instruction: 0x{:X}".format(ins & 0xffffffff))
            print(code)
            if 'XER' in isa_sim.spr:
                so = 1 if isa_sim.spr['XER'][XER_bits['SO']] else 0
                ov = 1 if isa_sim.spr['XER'][XER_bits['OV']] else 0
                ov32 = 1 if isa_sim.spr['XER'][XER_bits['OV32']] else 0
                print("before: so/ov/32", so, ov, ov32)

            # ask the decoder to decode this binary data (endian'd)
            yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
            yield instruction.eq(ins)          # raw binary instr.
            yield Delay(0.1e-6)
            fn_unit = yield pdecode2.e.do.fn_unit
            self.assertEqual(fn_unit, Function.MUL.value)
            pia_inputs = yield from set_alu_inputs(alu, pdecode2, isa_sim,
                                                   has_third_input)

            # set valid for one cycle, propagate through pipeline...
            yield alu.p.valid_i.eq(1)
            yield
            yield alu.p.valid_i.eq(0)

            opname = code.split(' ')[0]
            fnname = opname.replace(".", "_")
            print(f"{fnname}({pia_inputs})")
            pia_res = None
            try:
                pia_res = getattr(pia, fnname)(pia_inputs)
            except AttributeError:
                EXPECTED_FAILURES = ["mulli"]
                if fnname not in EXPECTED_FAILURES:
                    raise
                else:
                    print("not implemented, as expected.")
            print(f"-> {pia_res}")

            yield from isa_sim.call(opname)
            index = isa_sim.pc.CIA.value//4

            # ...wait for valid to pop out the end
            vld = yield alu.n.valid_o
            while not vld:
                yield
                yield Delay(0.1e-6)
                vld = yield alu.n.valid_o
            yield Delay(0.1e-6)

            # XXX sim._engine is an internal variable
            # Waiting on https://github.com/nmigen/nmigen/issues/443
            try:
                print(f"check time: {sim._engine.now * 1e6}us")
            except AttributeError:
                pass
            msg = (f"{code!r} {program.assembly!r} "
                   f"{list(map(hex, test.regs))!r}")
            yield from self.check_alu_outputs(alu, pdecode2, isa_sim, msg,
                                              pia_res)
            yield

    def run_all(self, test_data, file_name_prefix, has_third_input):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        fn_name = "MUL"
        opkls = MulPipeSpec.opsubsetkls

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(None, opkls, fn_name)
        pdecode = pdecode2.dec

        pspec = MulPipeSpec(id_wid=2)
        m.submodules.alu = alu = MulBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in test_data:
                print(test.name)
                with self.subTest(test.name):
                    yield from self.execute(pdecode2, test, instruction, alu,
                                            has_third_input, sim)

        sim.add_sync_process(process)
        with sim.write_vcd(f"{file_name_prefix}.vcd"):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code, pia_res):

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
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        print("res output", res)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        print("sim output", sim_o)

        print("power-instruction-analyzer result:")
        print(pia_res)
        if pia_res is not None:
            with self.subTest(check="pia", sim_o=sim_o, pia_res=str(pia_res)):
                pia_o = pia_res_to_output(pia_res)
                ALUHelpers.check_int_o(self, res, pia_o, code)
                ALUHelpers.check_cr_a(self, res, pia_o, code)
                ALUHelpers.check_xer_ov(self, res, pia_o, code)
                ALUHelpers.check_xer_so(self, res, pia_o, code)

        with self.subTest(check="sim", sim_o=sim_o, pia_res=str(pia_res)):
            ALUHelpers.check_int_o(self, res, sim_o, code)
            ALUHelpers.check_xer_ov(self, res, sim_o, code)
            ALUHelpers.check_xer_so(self, res, sim_o, code)
            ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
