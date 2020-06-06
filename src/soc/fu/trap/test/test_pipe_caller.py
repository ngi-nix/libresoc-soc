from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA


from soc.fu.test.common import TestCase
#from soc.fu.cr.pipeline import CRBasePipe
#from soc.fu.cr.pipe_data import CRPipeSpec
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


class TrapTestCase(FHDLTestCase):
    test_data = []
    def __init__(self, name):
        super().__init__(name)
        self.test_name = name


# def get_cu_inputs(dec2, sim):
#     """naming (res) must conform to CRFunctionUnit input regspec
#     """
#     res = {}
#     full_reg = yield dec2.e.read_cr_whole
#
#     # full CR
#     print(sim.cr.get_range().value)
#     if full_reg:
#         res['full_cr'] = sim.cr.get_range().value
#     else:
#         # CR A
#         cr1_en = yield dec2.e.read_cr1.ok
#         if cr1_en:
#             cr1_sel = yield dec2.e.read_cr1.data
#             res['cr_a'] = sim.crl[cr1_sel].get_range().value
#         cr2_en = yield dec2.e.read_cr2.ok
#         # CR B
#         if cr2_en:
#             cr2_sel = yield dec2.e.read_cr2.data
#             res['cr_b'] = sim.crl[cr2_sel].get_range().value
#         cr3_en = yield dec2.e.read_cr3.ok
#         # CR C
#         if cr3_en:
#             cr3_sel = yield dec2.e.read_cr3.data
#             res['cr_c'] = sim.crl[cr3_sel].get_range().value
#
#     # RA/RC
#     reg1_ok = yield dec2.e.read_reg1.ok
#     if reg1_ok:
#         data1 = yield dec2.e.read_reg1.data
#         res['ra'] = sim.gpr(data1).value
#
#     # RB (or immediate)
#     reg2_ok = yield dec2.e.read_reg2.ok
#     if reg2_ok:
#         data2 = yield dec2.e.read_reg2.data
#         res['rb'] = sim.gpr(data2).value
#
#     print ("get inputs", res)
#     return res


class TestRunner(FHDLTestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

#    def set_inputs(self, alu, dec2, simulator):
#        inp = yield from get_cu_inputs(dec2, simulator)
#        if 'full_cr' in inp:
#            yield alu.p.data_i.full_cr.eq(inp['full_cr'])
#        else:
#            yield alu.p.data_i.full_cr.eq(0)
#        if 'cr_a' in inp:
#            yield alu.p.data_i.cr_a.eq(inp['cr_a'])
#        if 'cr_b' in inp:
#            yield alu.p.data_i.cr_b.eq(inp['cr_b'])
#        if 'cr_c' in inp:
#            yield alu.p.data_i.cr_c.eq(inp['cr_c'])
#        if 'ra' in inp:
#            yield alu.p.data_i.ra.eq(inp['ra'])
#        else:
#            yield alu.p.data_i.ra.eq(0)
#        if 'rb' in inp:
#            yield alu.p.data_i.rb.eq(inp['rb'])
#        else:
#            yield alu.p.data_i.rb.eq(0)
#
#    def assert_outputs(self, alu, dec2, simulator, code):
#        whole_reg = yield dec2.e.write_cr_whole
#        cr_en = yield dec2.e.write_cr.ok
#        if whole_reg:
#            full_cr = yield alu.n.data_o.full_cr.data
#            expected_cr = simulator.cr.get_range().value
#            self.assertEqual(expected_cr, full_cr, code)
#        elif cr_en:
#            cr_sel = yield dec2.e.write_cr.data
#            expected_cr = simulator.crl[cr_sel].get_range().value
#            real_cr = yield alu.n.data_o.cr.data
#            self.assertEqual(expected_cr, real_cr, code)
#        alu_out = yield alu.n.data_o.o.data
#        out_reg_valid = yield dec2.e.write_reg.ok
#        if out_reg_valid:
#            write_reg_idx = yield dec2.e.write_reg.data
#            expected = simulator.gpr(write_reg_idx).value
#            print(f"expected {expected:x}, actual: {alu_out:x}")
#            self.assertEqual(expected, alu_out, code)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

#        pspec = CRPipeSpec(id_wid=2)
#        m.submodules.alu = alu = CRBasePipe(pspec)
#
#        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
#        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)
        def process():
            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                sim = ISA(pdecode2, test.regs, test.sprs, test.cr)
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
                    yield from self.set_inputs(alu, pdecode2, sim)
                    yield alu.p.valid_i.eq(1)
                    fn_unit = yield pdecode2.e.fn_unit
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

        sim.add_sync_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                            traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(TrapTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)