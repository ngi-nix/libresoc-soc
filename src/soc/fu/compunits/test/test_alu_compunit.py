from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, InternalOp)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA

from soc.fu.alu.test.test_pipe_caller import TestCase, ALUTestCase, test_data
from soc.fu.compunits.compunits import ALUFunctionUnit
import random

def set_cu_input(cu, idx, data):
    yield cu.src_i[idx].eq(data)
    while True:
        rd_rel_o = yield cu.rd.rel[idx]
        print ("rd_rel %d wait HI" % idx, rd_rel_o)
        if rd_rel_o:
            break
        yield
    yield cu.rd.go[idx].eq(1)
    while True:
        yield
        rd_rel_o = yield cu.rd.rel[idx]
        if rd_rel_o:
            break
        print ("rd_rel %d wait HI" % idx, rd_rel_o)
        yield
    yield cu.rd.go[idx].eq(0)


def get_cu_output(cu, idx):
    while True:
        wr_relall_o = yield cu.wr.rel
        wr_rel_o = yield cu.wr.rel[idx]
        print ("wr_rel %d wait" % idx, hex(wr_relall_o), wr_rel_o)
        if wr_rel_o:
            break
        yield
    yield cu.wr.go[idx].eq(1)
    yield
    result = yield cu.dest[idx]
    yield cu.wr.go[idx].eq(0)
    return result


def get_cu_rd_mask(dec2):

    mask = 0b1100 # XER CA/SO

    reg3_ok = yield dec2.e.read_reg3.ok
    reg1_ok = yield dec2.e.read_reg1.ok

    if reg3_ok or reg1_ok:
        mask |= 0b1

    # If there's an immediate, set the B operand to that
    reg2_ok = yield dec2.e.read_reg2.ok
    if reg2_ok:
        mask |= 0b10

    return mask


def set_cu_inputs(cu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    reg3_ok = yield dec2.e.read_reg3.ok
    reg1_ok = yield dec2.e.read_reg1.ok
    assert reg3_ok != reg1_ok
    if reg3_ok:
        data1 = yield dec2.e.read_reg3.data
        data1 = sim.gpr(data1).value
    elif reg1_ok:
        data1 = yield dec2.e.read_reg1.data
        data1 = sim.gpr(data1).value
    else:
        data1 = 0

    if reg3_ok or reg1_ok:
        yield from set_cu_input(cu, 0, data1)

    # If there's an immediate, set the B operand to that
    reg2_ok = yield dec2.e.read_reg2.ok
    if reg2_ok:
        data2 = yield dec2.e.read_reg2.data
        data2 = sim.gpr(data2).value
    else:
        data2 = 0

    if reg2_ok:
        yield from set_cu_input(cu, 1, data2)


def set_operand(cu, dec2, sim):
    yield from cu.oper_i.eq_from_execute1(dec2.e)
    yield cu.issue_i.eq(1)
    yield
    yield cu.issue_i.eq(0)
    yield


def set_extra_cu_inputs(cu, dec2, sim):
    carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
    carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
    yield from set_cu_input(cu, 3, carry | (carry32<<1))
    so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
    yield from set_cu_input(cu, 2, so)



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
        m.submodules.cu = cu = ALUFunctionUnit()

        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            yield cu.issue_i.eq(0)
            yield

            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                sim = ISA(pdecode2, test.regs, test.sprs, 0)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                index = sim.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("0x{:X}".format(ins & 0xffffffff))
                    print(code)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    fn_unit = yield pdecode2.e.fn_unit
                    self.assertEqual(fn_unit, Function.ALU.value)
                    # reset read-operand mask
                    rdmask = yield from get_cu_rd_mask(pdecode2)
                    yield cu.rdmaskn.eq(~rdmask)
                    yield from set_operand(cu, pdecode2, sim)
                    rd_rel_o = yield cu.rd.rel
                    wr_rel_o = yield cu.wr.rel
                    print ("before inputs, rd_rel, wr_rel: ",
                            bin(rd_rel_o), bin(wr_rel_o))
                    yield from set_cu_inputs(cu, pdecode2, sim)
                    yield from set_extra_cu_inputs(cu, pdecode2, sim)
                    yield
                    rd_rel_o = yield cu.rd.rel
                    wr_rel_o = yield cu.wr.rel
                    print ("after inputs, rd_rel, wr_rel: ",
                            bin(rd_rel_o), bin(wr_rel_o))
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    out_reg_valid = yield pdecode2.e.write_reg.ok
                    yield
                    yield
                    yield
                    if out_reg_valid:
                        write_reg_idx = yield pdecode2.e.write_reg.data
                        expected = sim.gpr(write_reg_idx).value
                        cu_out = yield from get_cu_output(cu, 0)
                        print(f"expected {expected:x}, actual: {cu_out:x}")
                        self.assertEqual(expected, cu_out, code)
                    yield
                    yield
                    yield
                    yield from self.check_extra_cu_outputs(cu, pdecode2,
                                                            sim, code)

                    yield Settle()
                    busy_o = yield cu.busy_o
                    if busy_o:
                        for i in range(cu.n_dst):
                            wr_rel_o = yield cu.wr.rel[i]
                            if wr_rel_o:
                                print ("discard output", i)
                                discard = yield from get_cu_output(cu, i)
                        yield

        sim.add_sync_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                            traces=[]):
            sim.run()

    def check_extra_cu_outputs(self, cu, dec2, sim, code):
        rc = yield dec2.e.rc.data
        op = yield dec2.e.insn_type

        if rc or \
           op == InternalOp.OP_CMP.value or \
           op == InternalOp.OP_CMPEQB.value:
            cr_actual = yield from get_cu_output(cu, 1)

        if rc:
            cr_expected = sim.crl[0].get_range().value
            self.assertEqual(cr_expected, cr_actual, code)

        if op == InternalOp.OP_CMP.value or \
           op == InternalOp.OP_CMPEQB.value:
            bf = yield dec2.dec.BF
            cr_expected = sim.crl[bf].get_range().value
            self.assertEqual(cr_expected, cr_actual, code)

        cry_out = yield dec2.e.output_carry
        if cry_out:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            xer_ca = yield from get_cu_output(cu, 2)
            real_carry = xer_ca & 0b1 # XXX CO not CO32
            self.assertEqual(expected_carry, real_carry, code)
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            real_carry32 = bool(xer_ca & 0b10) # XXX CO32
            self.assertEqual(expected_carry32, real_carry32, code)

        xer_ov = yield from get_cu_output(cu, 3)
        xer_so = yield from get_cu_output(cu, 4)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
