import random
import unittest
import power_instruction_analyzer as pia
from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Delay

from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_enums import XER_bits, Function
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian

from openpower.test.common import ALUHelpers
from soc.fu.test.pia import pia_res_to_output
from soc.fu.div.pipeline import DivBasePipe
from soc.fu.div.pipe_data import DivPipeSpec


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

    overflow = None
    if 'xer_so' in inp:
        so = inp['xer_so']
        overflow = pia.OverflowFlags(so=bool(so),
                                     ov=False,
                                     ov32=False)
    return pia.InstructionInput(ra=inp["ra"], rb=inp["rb"], overflow=overflow)


class DivTestHelper(unittest.TestCase):
    def execute(self, alu, instruction, pdecode2, test, div_pipe_kind, sim):
        prog = test.program
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
            pia_inputs = yield from set_alu_inputs(alu, pdecode2,
                                                   isa_sim)

            # set valid for one cycle, propagate through pipeline..
            # note that it is critically important to do this
            # for DIV otherwise it starts trying to produce
            # multiple results.
            yield alu.p.valid_i.eq(1)
            yield
            yield alu.p.valid_i.eq(0)

            opname = code.split(' ')[0]
            fnname = opname.replace(".", "_")
            print(f"{fnname}({pia_inputs})")
            pia_res = getattr(
                pia, opname.replace(".", "_"))(pia_inputs)
            print(f"-> {pia_res}")

            yield from isa_sim.call(opname)
            index = isa_sim.pc.CIA.value//4

            vld = yield alu.n.valid_o
            while not vld:
                yield
                yield Delay(0.1e-6)
                # XXX sim._engine is an internal variable
                # Waiting on https://github.com/nmigen/nmigen/issues/443
                try:
                    print(f"time: {sim._engine.now * 1e6}us")
                except AttributeError:
                    pass
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
                print("vld", vld)
                print("")

            yield Delay(0.1e-6)
            # XXX sim._engine is an internal variable
            # Waiting on https://github.com/nmigen/nmigen/issues/443
            try:
                print(f"check time: {sim._engine.now * 1e6}us")
            except AttributeError:
                pass
            msg = "%s: %s" % (div_pipe_kind.name, code)
            msg += f" {prog.assembly!r} {list(map(hex, test.regs))!r}"
            yield from self.check_alu_outputs(alu, pdecode2,
                                              isa_sim, msg,
                                              pia_res)
            yield

    def run_all(self, test_data, div_pipe_kind, file_name_prefix):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = DivPipeSpec(id_wid=2, div_pipe_kind=div_pipe_kind)
        m.submodules.alu = alu = DivBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.do)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in test_data:
                print(test.name)
                with self.subTest(test.name):
                    yield from self.execute(alu, instruction, pdecode2,
                                            test, div_pipe_kind, sim)

        sim.add_sync_process(process)
        with sim.write_vcd(f"{file_name_prefix}_{div_pipe_kind.name}.vcd"):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code, pia_res):

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
            ALUHelpers.check_cr_a(self, res, sim_o, code)
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
