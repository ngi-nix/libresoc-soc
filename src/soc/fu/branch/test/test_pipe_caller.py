from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, InternalOp)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.regfile.regfiles import FastRegs

from soc.fu.test.common import TestCase
from soc.fu.branch.pipeline import BranchBasePipe
from soc.fu.branch.pipe_data import BranchPipeSpec
import random

from soc.regfile.util import fast_reg_to_spr # HACK!


def get_rec_width(rec):
    recwidth = 0
    # Setup random inputs for dut.op
    for p in rec.ports():
        width = p.width
        recwidth += width
    return recwidth


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


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to BranchFunctionUnit input regspec
    """
    res = {}

    # CIA (PC)
    res['cia'] = sim.pc.CIA.value

    fast1_en = yield dec2.e.read_fast1.ok
    if fast1_en:
        fast1_sel = yield dec2.e.read_fast1.data
        spr1_sel = fast_reg_to_spr(fast1_sel)
        spr1_data = sim.spr[spr1_sel].value
        res['spr1'] = spr1_data

    fast2_en = yield dec2.e.read_fast2.ok
    if fast2_en:
        fast2_sel = yield dec2.e.read_fast2.data
        spr2_sel = fast_reg_to_spr(fast2_sel)
        spr2_data = sim.spr[spr2_sel].value
        res['spr2'] = spr2_data

    cr_en = yield dec2.e.read_cr1.ok
    if cr_en:
        cr_sel = yield dec2.e.read_cr1.data
        cr = sim.crl[cr_sel].get_range().value
        res['cr_a'] = cr

    print ("get inputs", res)
    return res


class BranchTestCase(FHDLTestCase):
    test_data = []
    def __init__(self, name):
        super().__init__(name)
        self.test_name = name

    def run_tst_program(self, prog, initial_regs=None,
                        initial_sprs=None, initial_cr=0):
        tc = TestCase(prog, self.test_name,
                      initial_regs, initial_sprs, initial_cr)
        self.test_data.append(tc)

    def test_unconditional(self):
        choices = ["b", "ba", "bl", "bla"]
        for i in range(20):
            choice = random.choice(choices)
            imm = random.randrange(-1<<23, (1<<23)-1) * 4
            lst = [f"{choice} {imm}"]
            initial_regs = [0] * 32
            self.run_tst_program(Program(lst), initial_regs)

    def test_bc_cr(self):
        for i in range(20):
            bc = random.randrange(-1<<13, (1<<13)-1) * 4
            bo = random.choice([0b01100, 0b00100, 0b10100])
            bi = random.randrange(0, 31)
            cr = random.randrange(0, (1<<32)-1)
            lst = [f"bc {bo}, {bi}, {bc}"]
            initial_regs = [0] * 32
            self.run_tst_program(Program(lst), initial_cr=cr)

    def test_bc_ctr(self):
        for i in range(20):
            bc = random.randrange(-1<<13, (1<<13)-1) * 4
            bo = random.choice([0, 2, 8, 10, 16, 18])
            bi = random.randrange(0, 31)
            cr = random.randrange(0, (1<<32)-1)
            ctr = random.randint(0, (1<<32)-1)
            lst = [f"bc {bo}, {bi}, {bc}"]
            initial_sprs={9: SelectableInt(ctr, 64)}
            self.run_tst_program(Program(lst),
                                 initial_sprs=initial_sprs,
                                 initial_cr=cr)

    def test_bc_reg(self):
        # XXX: bcctr and bcctrl time out (irony: they're counters)
        choices = ["bclr", "bclrl", "bcctr", "bcctrl", "bctar", "bctarl"]
        for insn in choices:
            for i in range(20):
                bh = random.randrange(0, 3)
                bo = random.choice([4, 12])
                bi = random.randrange(0, 31)
                cr = random.randrange(0, (1<<32)-1)
                ctr = random.randint(0, (1<<32)-1)
                lr = random.randint(0, (1<<64)-1) & ~3
                tar = random.randint(0, (1<<64)-1) & ~3
                lst = [f"{insn} {bo}, {bi}, {bh}"]
                initial_sprs={9: SelectableInt(ctr, 64),
                              8: SelectableInt(lr, 64),
                              815: SelectableInt(tar, 64)}
                self.run_tst_program(Program(lst),
                                     initial_sprs=initial_sprs,
                                     initial_cr=cr)

    def test_ilang(self):
        pspec = BranchPipeSpec(id_wid=2)
        alu = BranchBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("branch_pipeline.il", "w") as f:
            f.write(vl)


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

        pspec = BranchPipeSpec(id_wid=2)
        m.submodules.branch = branch = BranchBasePipe(pspec)

        comb += branch.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += branch.p.valid_i.eq(1)
        comb += branch.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)
        def process():
            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                simulator = ISA(pdecode2, test.regs, test.sprs, test.cr)
                initial_cia = 0x2000
                simulator.set_pc(initial_cia)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                index = (simulator.pc.CIA.value - initial_cia)//4
                while index < len(instructions) and index >= 0:
                    print(index)
                    ins, code = instructions[index]

                    print("0x{:X}".format(ins & 0xffffffff))
                    print(code)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    # note, here, the op will need further decoding in order
                    # to set the correct SPRs on SPR1/2/3.  op_bc* require
                    # spr1 to be set to CTR, op_bctar require spr2 to be
                    # set to TAR, op_bclr* require spr2 to be set to LR.
                    # if op_sc*, op_rf* and op_hrfid are to be added here
                    # then additional op-decoding is required, accordingly
                    yield Settle()
                    yield from self.set_inputs(branch, pdecode2, simulator)
                    fn_unit = yield pdecode2.e.fn_unit
                    self.assertEqual(fn_unit, Function.BRANCH.value, code)
                    yield
                    yield
                    opname = code.split(' ')[0]
                    prev_nia = simulator.pc.NIA.value
                    yield from simulator.call(opname)
                    index = (simulator.pc.CIA.value - initial_cia)//4

                    yield from self.assert_outputs(branch, pdecode2,
                                                   simulator, prev_nia, code)

        sim.add_sync_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                            traces=[]):
            sim.run()

    def assert_outputs(self, branch, dec2, sim, prev_nia, code):
        branch_taken = yield branch.n.data_o.nia.ok
        sim_branch_taken = prev_nia != sim.pc.CIA
        self.assertEqual(branch_taken, sim_branch_taken, code)
        if branch_taken:
            branch_addr = yield branch.n.data_o.nia.data
            print(f"real: {branch_addr:x}, sim: {sim.pc.CIA.value:x}")
            self.assertEqual(branch_addr, sim.pc.CIA.value, code)

        # TODO: check write_fast1 as well (should contain CTR)

        # TODO: this should be checking write_fast2
        lk = yield dec2.e.lk
        branch_lk = yield branch.n.data_o.lr.ok
        self.assertEqual(lk, branch_lk, code)
        if lk:
            branch_lr = yield branch.n.data_o.lr.data
            self.assertEqual(sim.spr['LR'], branch_lr, code)

    def set_inputs(self, branch, dec2, sim):
        print(f"cr0: {sim.crl[0].get_range()}")

        inp = yield from get_cu_inputs(dec2, sim)

        if 'cia' in inp:
            yield branch.p.data_i.cia.eq(inp['cia'])
        if 'spr1' in inp:
            yield branch.p.data_i.spr1.eq(inp['spr1'])
        if 'spr2' in inp:
            yield branch.p.data_i.spr2.eq(inp['spr2'])
        if 'cr_a' in inp:
            yield branch.p.data_i.cr.eq(inp['cr_a'])


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(BranchTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
