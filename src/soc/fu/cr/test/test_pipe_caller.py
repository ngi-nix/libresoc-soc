from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.config.endian import bigendian

from soc.fu.test.common import TestAccumulatorBase, TestCase, ALUHelpers
from soc.fu.test.common import mask_extend
from soc.fu.cr.pipeline import CRBasePipe
from soc.fu.cr.pipe_data import CRPipeSpec
import random


# This test bench is a bit different than is usual. Initially when I
# was writing it, I had all of the tests call a function to create a
# device under test and simulator, initialize the dut, run the
# simulation for ~2 cycles, and assert that the dut output what it
# should have. However, this was really slow, since it needed to
# create and tear down the dut and simulator for every test case.

# Now, instead of doing that, every test case in ALUTestCase puts some
# data into the test_data list below, describing the instructions to
# be tested and the initial state. Once all the tests have been run,
# test_data gets passed to TestRunner which then sets up the DUT and
# simulator once, runs all the data through it, and asserts that the
# results match the pseudocode sim at every cycle.

# By doing this, I've reduced the time it takes to run the test suite
# massively. Before, it took around 1 minute on my computer, now it
# takes around 3 seconds


class CRTestCase(TestAccumulatorBase):

    def case_crop(self):
        insns = ["crand", "cror", "crnand", "crnor", "crxor", "creqv",
                 "crandc", "crorc"]
        for i in range(40):
            choice = random.choice(insns)
            ba = random.randint(0, 31)
            bb = random.randint(0, 31)
            bt = random.randint(0, 31)
            lst = [f"{choice} {ba}, {bb}, {bt}"]
            cr = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_crand(self):
        for i in range(20):
            lst = ["crand 0, 11, 13"]
            cr = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_1_mcrf(self):
        for i in range(20):
            src = random.randint(0, 7)
            dst = random.randint(0, 7)
            lst = [f"mcrf {src}, {dst}"]
            cr = random.randint(0, (1 << 32)-1)
        self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_0_mcrf(self):
        for i in range(8):
            lst = [f"mcrf 5, {i}"]
            cr = 0xfeff0001
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_mtcrf(self):
        for i in range(1):
            mask = random.randint(0, 255)
            lst = [f"mtcrf {mask}, 2"]
            cr = random.randint(0, (1 << 32)-1)
            initial_regs = [0] * 32
            initial_regs[2] = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_regs=initial_regs,
                          initial_cr=cr)

    def case_mtocrf(self):
        for i in range(20):
            mask = 1 << random.randint(0, 7)
            lst = [f"mtocrf {mask}, 2"]
            cr = random.randint(0, (1 << 32)-1)
            initial_regs = [0] * 32
            initial_regs[2] = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_regs=initial_regs,
                          initial_cr=cr)

    def case_mfcr(self):
        for i in range(1):
            lst = ["mfcr 2"]
            cr = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_mfocrf_regression(self):
        """bit of a bad hack.  comes from microwatt 1.bin instruction 0x106d0
        as the mask is non-standard, gnu-as barfs.  so we fake it up directly
        from the binary
        """
        mask = 0b10000111
        dis = [f"mfocrf 2, {mask}"]
        lst = bytes([0x26, 0x78, 0xb8, 0x7c]) # 0x7cb87826
        cr = 0x5F9E080E
        p = Program(lst, bigendian)
        p.assembly = '\n'.join(dis)+'\n'
        self.add_case(p, initial_cr=cr)

    def case_mfocrf_1(self):
        lst = [f"mfocrf 2, 1"]
        cr = 0x1234
        self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_mfocrf(self):
        for i in range(1):
            mask = 1 << random.randint(0, 7)
            lst = [f"mfocrf 2, {mask}"]
            cr = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_isel(self):
        for i in range(20):
            bc = random.randint(0, 31)
            lst = [f"isel 1, 2, 3, {bc}"]
            cr = random.randint(0, (1 << 64)-1)
            initial_regs = [0] * 32
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            initial_regs[3] = random.randint(0, (1 << 64)-1)
            #initial_regs[2] = i*2
            #initial_regs[3] = i*2+1
            self.add_case(Program(lst, bigendian),
                          initial_regs=initial_regs, initial_cr=cr)

    def case_setb(self):
        for i in range(20):
            bfa = random.randint(0, 7)
            lst = [f"setb 1, {bfa}"]
            cr = random.randint(0, (1 << 32)-1)
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_regression_setb(self):
        lst = [f"setb 1, 6"]
        cr = random.randint(0, 0x66f6b106)
        self.add_case(Program(lst, bigendian), initial_cr=cr)

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
    full_reg = yield dec2.e.do.read_cr_whole.data
    full_reg_ok = yield dec2.e.do.read_cr_whole.ok
    full_cr_mask = mask_extend(full_reg, 8, 4)

    # full CR
    print(sim.cr.get_range().value)
    if full_reg_ok:
        res['full_cr'] = sim.cr.get_range().value & full_cr_mask
    else:
        # CR A
        cr1_en = yield dec2.e.read_cr1.ok
        if cr1_en:
            cr1_sel = yield dec2.e.read_cr1.data
            res['cr_a'] = sim.crl[cr1_sel].get_range().value
        cr2_en = yield dec2.e.read_cr2.ok
        # CR B
        if cr2_en:
            cr2_sel = yield dec2.e.read_cr2.data
            res['cr_b'] = sim.crl[cr2_sel].get_range().value
        cr3_en = yield dec2.e.read_cr3.ok
        # CR C
        if cr3_en:
            cr3_sel = yield dec2.e.read_cr3.data
            res['cr_c'] = sim.crl[cr3_sel].get_range().value

    # RA/RC
    reg1_ok = yield dec2.e.read_reg1.ok
    if reg1_ok:
        data1 = yield dec2.e.read_reg1.data
        res['ra'] = sim.gpr(data1).value

    # RB (or immediate)
    reg2_ok = yield dec2.e.read_reg2.ok
    if reg2_ok:
        data2 = yield dec2.e.read_reg2.data
        res['rb'] = sim.gpr(data2).value

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
        whole_reg_ok = yield dec2.e.do.write_cr_whole.ok
        whole_reg_data = yield dec2.e.do.write_cr_whole.data
        full_cr_mask = mask_extend(whole_reg_data, 8, 4)

        cr_en = yield dec2.e.write_cr.ok
        if whole_reg_ok:
            full_cr = yield alu.n.data_o.full_cr.data & full_cr_mask
            expected_cr = simulator.cr.get_range().value
            print("CR whole: expected %x, actual: %x mask: %x" % \
                (expected_cr, full_cr, full_cr_mask))
            # HACK: only look at the bits that we expected to change
            self.assertEqual(expected_cr & full_cr_mask, full_cr, code)
        elif cr_en:
            cr_sel = yield dec2.e.write_cr.data
            expected_cr = simulator.cr.get_range().value
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

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = CRPipeSpec(id_wid=2)
        m.submodules.alu = alu = CRBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
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

    runner = unittest.TextTestRunner()
    runner.run(suite)
