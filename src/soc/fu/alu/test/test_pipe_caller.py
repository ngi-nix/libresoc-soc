from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, InternalOp, CryIn)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA


from soc.fu.test.common import TestCase
from soc.fu.alu.pipeline import ALUBasePipe
from soc.fu.alu.pipe_data import ALUPipeSpec
import random


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to ALUFunctionUnit input regspec
    """
    res = {}

    # RA (or RC)
    reg1_ok = yield dec2.e.read_reg1.ok
    if reg1_ok:
        data1 = yield dec2.e.read_reg1.data
        res['ra'] = sim.gpr(data1).value

    # RB (or immediate)
    reg2_ok = yield dec2.e.read_reg2.ok
    if reg2_ok:
        data2 = yield dec2.e.read_reg2.data
        res['rb'] = sim.gpr(data2).value

    # XER.ca
    cry_in = yield dec2.e.input_carry
    if cry_in == CryIn.CA.value:
        carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
        carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
        res['xer_ca'] = carry | (carry32<<1)

    # XER.so
    oe = yield dec2.e.oe.data[0] & dec2.e.oe.ok
    if oe:
        so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
        res['xer_so'] = so

    print ("alu get_cu_inputs", res)

    return res



def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    if 'ra' in inp:
        yield alu.p.data_i.a.eq(inp['ra'])
    if 'rb' in inp:
        yield alu.p.data_i.b.eq(inp['rb'])

    # If there's an immediate, set the B operand to that
    imm_ok = yield dec2.e.imm_data.imm_ok
    if imm_ok:
        data2 = yield dec2.e.imm_data.imm
        yield alu.p.data_i.b.eq(data2)

    if 'xer_ca' in inp:
        yield alu.p.data_i.xer_ca.eq(inp['xer_ca'])
        print ("extra inputs: CA/32", bin(inp['xer_ca']))
    if 'xer_so' in inp:
        so = inp['xer_so']
        print ("extra inputs: so", so)
        yield alu.p.data_i.xer_so.eq(so)


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


class ALUTestCase(FHDLTestCase):
    test_data = []

    def __init__(self, name):
        super().__init__(name)
        self.test_name = name

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None):
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs)
        self.test_data.append(tc)

    def test_1_regression(self):
        lst = [f"extsw 3, 1"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xb6a1fc6c8576af91
        self.run_tst_program(Program(lst), initial_regs)
        lst = [f"subf 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3d7f3f7ca24bac7b
        initial_regs[2] = 0xf6b2ac5e13ee15c2
        self.run_tst_program(Program(lst), initial_regs)
        lst = [f"subf 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x833652d96c7c0058
        initial_regs[2] = 0x1c27ecff8a086c1a
        self.run_tst_program(Program(lst), initial_regs)
        lst = [f"extsb 3, 1"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7f9497aaff900ea0
        self.run_tst_program(Program(lst), initial_regs)
        lst = [f"add. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xc523e996a8ff6215
        initial_regs[2] = 0xe1e5b9cc9864c4a8
        self.run_tst_program(Program(lst), initial_regs)
        lst = [f"add 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x2e08ae202742baf8
        initial_regs[2] = 0x86c43ece9efe5baa
        self.run_tst_program(Program(lst), initial_regs)

    def test_rand(self):
        insns = ["add", "add.", "subf"]
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

    def test_0_adde(self):
        lst = ["adde. 5, 6, 7"]
        for i in range(10):
            initial_regs = [0] * 32
            initial_regs[6] = random.randint(0, (1<<64)-1)
            initial_regs[7] = random.randint(0, (1<<64)-1)
            initial_sprs = {}
            xer = SelectableInt(0, 64)
            xer[XER_bits['CA']] = 1
            initial_sprs[special_sprs['XER']] = xer
            self.run_tst_program(Program(lst), initial_regs, initial_sprs)

    def test_cmp(self):
        lst = ["subf. 1, 6, 7",
               "cmp cr2, 1, 6, 7"]
        initial_regs = [0] * 32
        initial_regs[6] = 0x10
        initial_regs[7] = 0x05
        self.run_tst_program(Program(lst), initial_regs, {})

    def test_extsb(self):
        insns = ["extsb", "extsh", "extsw"]
        for i in range(10):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            self.run_tst_program(Program(lst), initial_regs)

    def test_cmpeqb(self):
        lst = ["cmpeqb cr1, 1, 2"]
        for i in range(20):
            initial_regs = [0] * 32
            initial_regs[1] = i
            initial_regs[2] = 0x0001030507090b0f
            self.run_tst_program(Program(lst), initial_regs, {})

    def test_ilang(self):
        pspec = ALUPipeSpec(id_wid=2)
        alu = ALUBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("alu_pipeline.il", "w") as f:
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

        pspec = ALUPipeSpec(id_wid=2)
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
                sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                                test.mem, test.msr)
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
                        print ("before: so/ov/32", so, ov, ov32)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    fn_unit = yield pdecode2.e.fn_unit
                    self.assertEqual(fn_unit, Function.ALU.value)
                    yield from set_alu_inputs(alu, pdecode2, sim)
                    yield
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    vld = yield alu.n.valid_o
                    while not vld:
                        yield
                        vld = yield alu.n.valid_o
                    yield
                    alu_out = yield alu.n.data_o.o.data
                    out_reg_valid = yield pdecode2.e.write_reg.ok
                    if out_reg_valid:
                        write_reg_idx = yield pdecode2.e.write_reg.data
                        expected = sim.gpr(write_reg_idx).value
                        print(f"expected {expected:x}, actual: {alu_out:x}")
                        self.assertEqual(expected, alu_out, code)
                    yield from self.check_extra_alu_outputs(alu, pdecode2,
                                                            sim, code)

        sim.add_sync_process(process)
        with sim.write_vcd("alu_simulator.vcd", "simulator.gtkw",
                            traces=[]):
            sim.run()

    def check_extra_alu_outputs(self, alu, dec2, sim, code):
        rc = yield dec2.e.rc.data
        op = yield dec2.e.insn_type
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print ("check extra output", repr(code), cridx_ok, cridx)
        if rc:
            self.assertEqual(cridx, 0, code)

        if cridx_ok:
            cr_expected = sim.crl[cridx].get_range().value
            cr_actual = yield alu.n.data_o.cr0.data
            print ("CR", cridx, cr_expected, cr_actual)
            self.assertEqual(cr_expected, cr_actual, "CR%d %s" % (cridx, code))

        cry_out = yield dec2.e.output_carry
        if cry_out:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            real_carry = yield alu.n.data_o.xer_ca.data[0] # XXX CA not CA32
            self.assertEqual(expected_carry, real_carry, code)
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            real_carry32 = yield alu.n.data_o.xer_ca.data[1] # XXX CA32
            self.assertEqual(expected_carry32, real_carry32, code)

        oe = yield dec2.e.oe.oe
        oe_ok = yield dec2.e.oe.ok
        if oe and oe_ok:
            expected_so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
            real_so = yield alu.n.data_o.xer_so.data[0]
            self.assertEqual(expected_so, real_so, code)
            expected_ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
            real_ov = yield alu.n.data_o.xer_ov.data[0] # OV bit
            self.assertEqual(expected_ov, real_ov, code)
            expected_ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
            real_ov32 = yield alu.n.data_o.xer_ov.data[1] # OV32 bit
            self.assertEqual(expected_ov32, real_ov32, code)
            print ("after: so/ov/32", real_so, real_ov, real_ov32)
        else:
            # if OE not enabled, XER SO and OV must correspondingly be false
            so_ok = yield alu.n.data_o.xer_so.ok
            ov_ok = yield alu.n.data_o.xer_ov.ok
            self.assertEqual(so_ok, False, code)
            self.assertEqual(ov_ok, False, code)



if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(ALUTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
