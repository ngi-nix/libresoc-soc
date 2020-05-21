from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA


from soc.fu.cr.pipeline import CRBasePipe
from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.cr.pipe_data import CRPipeSpec
import random


class TestCase:
    def __init__(self, program, regs, sprs, cr, name):
        self.program = program
        self.regs = regs
        self.sprs = sprs
        self.name = name
        self.cr = cr


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

test_data = []


class CRTestCase(FHDLTestCase):
    def __init__(self, name):
        super().__init__(name)
        self.test_name = name
    def run_tst_program(self, prog, initial_regs=[0] * 32, initial_sprs={},
                        initial_cr=0):
        tc = TestCase(prog, initial_regs, initial_sprs, initial_cr,
                      self.test_name)
        test_data.append(tc)

    def test_crop(self):
        insns = ["crand", "cror", "crnand", "crnor", "crxor", "creqv",
                 "crandc", "crorc"]
        for i in range(40):
            choice = random.choice(insns)
            ba = random.randint(0, 31)
            bb = random.randint(0, 31)
            bt = random.randint(0, 31)
            lst = [f"{choice} {ba}, {bb}, {bt}"]
            cr = random.randint(0, 7)
            self.run_tst_program(Program(lst), initial_cr=cr)

    def test_mcrf(self):
        lst = ["mcrf 0, 5"]
        cr = 0xffff0000
        self.run_tst_program(Program(lst), initial_cr=cr)

    def test_mtcrf(self):
        for i in range(20):
            mask = random.randint(0, 255)
            lst = [f"mtcrf {mask}, 2"]
            cr = random.randint(0, (1<<32)-1)
            initial_regs = [0] * 32
            initial_regs[2] = random.randint(0, (1<<32)-1)
            self.run_tst_program(Program(lst), initial_regs=initial_regs,
                                 initial_cr=cr)
    def test_mtocrf(self):
        for i in range(20):
            mask = 1<<random.randint(0, 7)
            lst = [f"mtocrf {mask}, 2"]
            cr = random.randint(0, (1<<32)-1)
            initial_regs = [0] * 32
            initial_regs[2] = random.randint(0, (1<<32)-1)
            self.run_tst_program(Program(lst), initial_regs=initial_regs,
                                 initial_cr=cr)

    def test_mfcr(self):
        for i in range(5):
            lst = ["mfcr 2"]
            cr = random.randint(0, (1<<32)-1)
            self.run_tst_program(Program(lst), initial_cr=cr)

    def test_mfocrf(self):
        for i in range(20):
            mask = 1<<random.randint(0, 7)
            lst = [f"mfocrf 2, {mask}"]
            cr = random.randint(0, (1<<32)-1)
            self.run_tst_program(Program(lst), initial_cr=cr)
        

    def test_ilang(self):
        pspec = CRPipeSpec(id_wid=2)
        alu = CRBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("cr_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(FHDLTestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def set_inputs(self, alu, dec2, simulator):
        yield alu.p.data_i.cr.eq(simulator.cr.get_range().value)

        reg3_ok = yield dec2.e.read_reg3.ok
        if reg3_ok:
            reg3_sel = yield dec2.e.read_reg3.data
            reg3 = simulator.gpr(reg3_sel).value
            yield alu.p.data_i.a.eq(reg3)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = CRPipeSpec(id_wid=2)
        m.submodules.alu = alu = CRBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.p.valid_i.eq(1)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)
        def process():
            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                simulator = ISA(pdecode2, test.regs, test.sprs, test.cr)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                index = simulator.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("0x{:X}".format(ins & 0xffffffff))
                    print(code)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    yield from self.set_inputs(alu, pdecode2, simulator)
                    fn_unit = yield pdecode2.e.fn_unit
                    self.assertEqual(fn_unit, Function.CR.value, code)
                    yield 
                    opname = code.split(' ')[0]
                    yield from simulator.call(opname)
                    index = simulator.pc.CIA.value//4

                    vld = yield alu.n.valid_o
                    while not vld:
                        yield
                        vld = yield alu.n.valid_o
                    yield
                    cr_out = yield pdecode2.e.output_cr
                    if cr_out:
                        cr_expected = simulator.cr.get_range().value
                        cr_real = yield alu.n.data_o.cr
                        msg = f"real: {cr_expected:x}, actual: {cr_real:x}"
                        msg += " code: %s" % code
                        self.assertEqual(cr_expected, cr_real, msg)

                    reg_out = yield pdecode2.e.write_reg.ok
                    if reg_out:
                        reg_sel = yield pdecode2.e.write_reg.data
                        reg_data = simulator.gpr(reg_sel).value
                        output = yield alu.n.data_o.o
                        msg = f"real: {reg_data:x}, actual: {output:x}"
                        self.assertEqual(reg_data, output)

        sim.add_sync_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                            traces=[]):
            sim.run()
    def check_extra_alu_outputs(self, alu, dec2, sim):
        rc = yield dec2.e.rc.data
        if rc:
            cr_expected = sim.crl[0].get_range().value
            cr_actual = yield alu.n.data_o.cr0
            self.assertEqual(cr_expected, cr_actual)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
