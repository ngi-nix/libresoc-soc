from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, MicrOp)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.regfile.regfiles import FastRegs
from soc.config.endian import bigendian

from soc.fu.test.common import TestAccumulatorBase, TestCase, ALUHelpers
from soc.fu.branch.pipeline import BranchBasePipe
from soc.fu.branch.pipe_data import BranchPipeSpec
import random

from soc.regfile.util import fast_reg_to_spr  # HACK!


def get_rec_width(rec):
    recwidth = 0
    # Setup random inputs for dut.op
    for p in rec.ports():
        width = p.width
        recwidth += width
    return recwidth


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to BranchFunctionUnit input regspec
    """
    res = {}

    # CIA (PC)
    #res['cia'] = sim.pc.CIA.value

    yield from ALUHelpers.get_sim_fast_spr1(res, sim, dec2)
    yield from ALUHelpers.get_sim_fast_spr2(res, sim, dec2)
    yield from ALUHelpers.get_sim_cr_a(res, sim, dec2)

    print("get inputs", res)
    return res


class BranchTestCase(TestAccumulatorBase):

    def case_0_regression_unconditional(self):
        for i in range(2):
            imm = random.randrange(-1 << 23, (1 << 23)-1) * 4
            lst = [f"bl {imm}"]
            initial_regs = [0] * 32
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_unconditional(self):
        choices = ["b", "ba", "bl", "bla"]
        for i in range(20):
            choice = random.choice(choices)
            imm = random.randrange(-1 << 23, (1 << 23)-1) * 4
            lst = [f"{choice} {imm}"]
            initial_regs = [0] * 32
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_bc_cr(self):
        for i in range(20):
            bc = random.randrange(-1 << 13, (1 << 13)-1) * 4
            bo = random.choice([0b01100, 0b00100, 0b10100])
            bi = random.randrange(0, 31)
            cr = random.randrange(0, (1 << 32)-1)
            lst = [f"bc {bo}, {bi}, {bc}"]
            initial_regs = [0] * 32
            self.add_case(Program(lst, bigendian), initial_cr=cr)

    def case_bc_ctr(self):
        for i in range(20):
            bc = random.randrange(-1 << 13, (1 << 13)-1) * 4
            bo = random.choice([0, 2, 8, 10, 16, 18])
            bi = random.randrange(0, 31)
            cr = random.randrange(0, (1 << 32)-1)
            ctr = random.randint(0, (1 << 32)-1)
            lst = [f"bc {bo}, {bi}, {bc}"]
            initial_sprs = {9: SelectableInt(ctr, 64)}
            self.add_case(Program(lst, bigendian),
                          initial_sprs=initial_sprs,
                          initial_cr=cr)

    def case_bc_reg(self):
        # XXX: bcctr and bcctrl time out (irony: they're counters)
        choices = ["bclr", "bclrl", "bcctr", "bcctrl", "bctar", "bctarl"]
        for insn in choices:
            for i in range(20):
                bh = random.randrange(0, 3)
                bo = random.choice([4, 12])
                bi = random.randrange(0, 31)
                cr = random.randrange(0, (1 << 32)-1)
                ctr = random.randint(0, (1 << 32)-1)
                lr = random.randint(0, (1 << 64)-1) & ~3
                tar = random.randint(0, (1 << 64)-1) & ~3
                lst = [f"{insn} {bo}, {bi}, {bh}"]
                initial_sprs = {9: SelectableInt(ctr, 64),
                                8: SelectableInt(lr, 64),
                                815: SelectableInt(tar, 64)}
                self.add_case(Program(lst, bigendian),
                              initial_sprs=initial_sprs,
                              initial_cr=cr)

    def case_bc_microwatt_1_regression(self):
        """bc found to be testing ctr rather than (ctr-1)
        11fb4:   08 00 49 40     bc      2,4*cr2+gt,0x11fbc
        cr_file.vhdl:83:13:@136835ns:(report note): Reading CR 33209703
        """
        lst = ["bc 2, 9, 8"]
        initial_regs = [0] * 32
        cr = 0x33209703
        self.add_case(Program(lst, bigendian), initial_regs,
                              initial_cr=cr)

    def case_bc_microwatt_2_regression(self):
        """modified version, set CTR=1 so that it hits zero in BC
        """
        lst = ["bc 2, 9, 8"]
        initial_regs = [0] * 32
        cr = 0x33209703
        ctr = 1
        initial_sprs = {9: SelectableInt(ctr, 64),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                              initial_sprs=initial_sprs,
                              initial_cr=cr)

    def case_ilang(self):
        pspec = BranchPipeSpec(id_wid=2)
        alu = BranchBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("branch_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(unittest.TestCase):
    def test_it(self):
        test_data = BranchTestCase().test_data
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        fn_name = "BRANCH"
        opkls = BranchPipeSpec.opsubsetkls

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(None, opkls, fn_name)
        pdecode = pdecode2.dec

        # copy of the decoder for simulator
        simdec = create_pdecode()
        simdec2 = PowerDecode2(simdec)
        m.submodules.simdec2 = simdec2  # pain in the neck

        pspec = BranchPipeSpec(id_wid=2)
        m.submodules.branch = branch = BranchBasePipe(pspec)

        comb += branch.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += branch.p.valid_i.eq(1)
        comb += branch.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in test_data:
                print(test.name)
                program = test.program
                with self.subTest(test.name):
                    simulator = ISA(simdec2, test.regs, test.sprs, test.cr,
                                    test.mem, test.msr,
                                    bigendian=bigendian)
                    initial_cia = 0x2000
                    simulator.set_pc(initial_cia)
                    gen = program.generate_instructions()
                    instructions = list(
                        zip(gen, program.assembly.splitlines()))

                    pc = simulator.pc.CIA.value
                    msr = simulator.msr.value
                    index = (pc - initial_cia)//4
                    while index < len(instructions) and index >= 0:
                        print(index)
                        ins, code = instructions[index]

                        print("0x{:X}".format(ins & 0xffffffff))
                        print(code)

                        # ask the decoder to decode this binary data (endian'd)
                        # little / big?
                        yield pdecode2.dec.bigendian.eq(bigendian)
                        yield pdecode2.state.msr.eq(msr)  # set MSR in pdecode2
                        yield pdecode2.state.pc.eq(pc)  # set PC in pdecode2
                        yield instruction.eq(ins)          # raw binary instr.
                        # note, here, the op will need further decoding in order
                        # to set the correct SPRs on SPR1/2/3.  op_bc* require
                        # spr1 to be set to CTR, op_bctar require spr2 to be
                        # set to TAR, op_bclr* require spr2 to be set to LR.
                        # if op_sc*, op_rf* and op_hrfid are to be added here
                        # then additional op-decoding is required, accordingly
                        yield Settle()
                        lk = yield pdecode2.e.do.lk
                        print("lk:", lk)
                        yield from self.set_inputs(branch, pdecode2, simulator)
                        fn_unit = yield pdecode2.e.do.fn_unit
                        self.assertEqual(fn_unit, Function.BRANCH.value, code)
                        yield
                        yield
                        opname = code.split(' ')[0]
                        prev_nia = simulator.pc.NIA.value
                        yield from simulator.call(opname)
                        pc = simulator.pc.CIA.value
                        msr = simulator.msr.value
                        index = (pc - initial_cia)//4

                        yield from self.assert_outputs(branch, pdecode2,
                                                       simulator, prev_nia,
                                                       code)

        sim.add_sync_process(process)
        with sim.write_vcd("branch_simulator.vcd"):
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
        lk = yield dec2.e.do.lk
        branch_lk = yield branch.n.data_o.lr.ok
        self.assertEqual(lk, branch_lk, code)
        if lk:
            branch_lr = yield branch.n.data_o.lr.data
            self.assertEqual(sim.spr['LR'], branch_lr, code)

    def set_inputs(self, branch, dec2, sim):
        print(f"cr0: {sim.crl[0].get_range()}")

        inp = yield from get_cu_inputs(dec2, sim)

        yield from ALUHelpers.set_fast_spr1(branch, dec2, inp)
        yield from ALUHelpers.set_fast_spr2(branch, dec2, inp)
        yield from ALUHelpers.set_cr_a(branch, dec2, inp)


if __name__ == "__main__":
    unittest.main()
