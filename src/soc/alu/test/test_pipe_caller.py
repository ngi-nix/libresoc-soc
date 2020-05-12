from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA


from soc.alu.pipeline import ALUBasePipe
from soc.alu.alu_input_record import CompALUOpSubset
from soc.alu.pipe_data import ALUPipeSpec
import random

class TestCase:
    def __init__(self, program, regs, sprs, name):
        self.program = program
        self.regs = regs
        self.sprs = sprs
        self.name = name

def get_rec_width(rec):
    recwidth = 0
    # Setup random inputs for dut.op
    for p in rec.ports():
        width = p.width
        recwidth += width
    return recwidth

def set_alu_inputs(alu, dec2, sim):
    inputs = []
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    reg3_ok = yield dec2.e.read_reg3.ok
    if reg3_ok:
        data3 = yield dec2.e.read_reg3.data
        data3 = sim.gpr(data3).value
        inputs.append(data3)
    else:
        data3 = 0

    reg1_ok = yield dec2.e.read_reg1.ok
    if reg1_ok:
        data1 = yield dec2.e.read_reg1.data
        data1 = sim.gpr(data1).value
        inputs.append(data1)
    else:
        data1 = 0

    # If there's an immediate, set the B operand to that
    reg2_ok = yield dec2.e.read_reg2.ok
    imm_ok = yield dec2.e.imm_data.imm_ok
    if imm_ok:
        data2 = yield dec2.e.imm_data.imm
        inputs.append(data2)
    elif reg2_ok:
        data2 = yield dec2.e.read_reg2.data
        data2 = sim.gpr(data2).value
        inputs.append(data2)
    else:
        data2 = 0

    print("inputs", inputs)

    if len(inputs) == 0:
        yield alu.p.data_i.a.eq(0)
        yield alu.p.data_i.b.eq(0)
    if len(inputs) == 1:
        yield alu.p.data_i.a.eq(inputs[0])
        yield alu.p.data_i.b.eq(0)
    if len(inputs) == 2:
        yield alu.p.data_i.a.eq(inputs[0])
        yield alu.p.data_i.b.eq(inputs[1])


def set_extra_alu_inputs(alu, dec2, sim):
    carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
    yield alu.p.data_i.carry_in.eq(carry)
    so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
    yield alu.p.data_i.so.eq(so)
    

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


class ALUTestCase(FHDLTestCase):
    def __init__(self, name):
        super().__init__(name)
        self.test_name = name
    def run_tst_program(self, prog, initial_regs=[0] * 32, initial_sprs={}):
        tc = TestCase(prog, initial_regs, initial_sprs, self.test_name)
        test_data.append(tc)

    def test_rand(self):
        insns = ["add", "add.", "and", "or", "xor", "subf"]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            initial_regs[2] = random.randint(0, (1<<64)-1)
            self.run_tst_program(Program(lst), initial_regs)

    def test_rand_imm(self):
        insns = ["addi", "addis", "subfic"]
        for i in range(10):
            choice = random.choice(insns)
            imm = random.randint(-(1<<15), (1<<15)-1)
            lst = [f"{choice} 3, 1, {imm}"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            self.run_tst_program(Program(lst), initial_regs)

    def test_rand_imm_logical(self):
        insns = ["andi.", "andis.", "ori", "oris", "xori", "xoris"]
        for i in range(10):
            choice = random.choice(insns)
            imm = random.randint(0, (1<<16)-1)
            lst = [f"{choice} 3, 1, {imm}"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            self.run_tst_program(Program(lst), initial_regs)
        
    def test_adde(self):
        lst = ["adde. 5, 6, 7"]
        initial_regs = [0] * 32
        initial_regs[6] = random.randint(0, (1<<64)-1)
        initial_regs[7] = random.randint(0, (1<<64)-1)
        initial_sprs = {}
        xer = SelectableInt(0, 64)
        xer[XER_bits['CA']] = 1
        initial_sprs[special_sprs['XER']] = xer
        self.run_tst_program(Program(lst), initial_regs, initial_sprs)

    def test_ilang(self):
        rec = CompALUOpSubset()

        pspec = ALUPipeSpec(id_wid=2, op_wid=get_rec_width(rec))
        alu = ALUBasePipe(pspec)
        vl = rtlil.convert(alu, ports=[])
        with open("pipeline.il", "w") as f:
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

        rec = CompALUOpSubset()

        pspec = ALUPipeSpec(id_wid=2, op_wid=get_rec_width(rec))
        m.submodules.alu = alu = ALUBasePipe(pspec)

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
                simulator = ISA(pdecode2, test.regs, test.sprs)
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
                    yield from set_alu_inputs(alu, pdecode2, simulator)
                    yield from set_extra_alu_inputs(alu, pdecode2, simulator)
                    yield 
                    opname = code.split(' ')[0]
                    yield from simulator.call(opname)
                    index = simulator.pc.CIA.value//4

                    vld = yield alu.n.valid_o
                    while not vld:
                        yield
                        vld = yield alu.n.valid_o
                    yield
                    alu_out = yield alu.n.data_o.o
                    out_reg_valid = yield pdecode2.e.write_reg.ok
                    if out_reg_valid:
                        write_reg_idx = yield pdecode2.e.write_reg.data
                        expected = simulator.gpr(write_reg_idx).value
                        print(f"expected {expected:x}, actual: {alu_out:x}")
                        self.assertEqual(expected, alu_out)
                    yield from self.check_extra_alu_outputs(alu, pdecode2,
                                                            simulator)

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
