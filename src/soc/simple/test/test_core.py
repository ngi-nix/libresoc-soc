"""simple core test

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""
from nmigen import Module, Signal, Cat
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import special_sprs
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2
from soc.decoder.isa.all import ISA
from soc.decoder.power_enums import Function, XER_bits


from soc.simple.core import NonProductionCore
from soc.experiment.compalu_multi import find_ok # hack

# test with ALU data and Logical data
from soc.fu.alu.test.test_pipe_caller import ALUTestCase
from soc.fu.logical.test.test_pipe_caller import LogicalTestCase
from soc.fu.shift_rot.test.test_pipe_caller import ShiftRotTestCase
from soc.fu.cr.test.test_pipe_caller import CRTestCase
from soc.fu.branch.test.test_pipe_caller import BranchTestCase


def set_issue(core, dec2, sim):
    yield core.issue_i.eq(1)
    yield
    yield core.issue_i.eq(0)
    while True:
        busy_o = yield core.busy_o
        if busy_o:
            break
        print("!busy",)
        yield


def wait_for_busy_clear(cu):
    while True:
        busy_o = yield cu.busy_o
        if not busy_o:
            break
        print("busy",)
        yield


class TestRunner(FHDLTestCase):
    def __init__(self, tst_data):
        super().__init__("run_all")
        self.test_data = tst_data

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)
        ivalid_i = Signal()

        m.submodules.core = core = NonProductionCore()
        pdecode = core.pdecode
        pdecode2 = core.pdecode2

        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        comb += core.ivalid_i.eq(ivalid_i)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            yield core.issue_i.eq(0)
            yield

            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                sim = ISA(pdecode2, test.regs, test.sprs, test.cr, test.mem,
                          test.msr)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                # set up INT regfile, "direct" write (bypass rd/write ports)
                for i in range(32):
                    yield core.regs.int.regs[i].reg.eq(test.regs[i])

                # set up CR regfile, "direct" write across all CRs
                cr = test.cr
                #cr = int('{:32b}'.format(cr)[::-1], 2)
                print ("cr reg", hex(cr))
                for i in range(8):
                    #j = 7-i
                    cri = (cr>>(i*4)) & 0xf
                    #cri = int('{:04b}'.format(cri)[::-1], 2)
                    print ("cr reg", hex(cri), i,
                            core.regs.cr.regs[i].reg.shape())
                    yield core.regs.cr.regs[i].reg.eq(cri)

                # set up XER.  "direct" write (bypass rd/write ports)
                xregs = core.regs.xer
                print ("sprs", test.sprs)
                if special_sprs['XER'] in test.sprs:
                    xer = test.sprs[special_sprs['XER']]
                    sobit = xer[XER_bits['SO']].asint()
                    yield xregs.regs[xregs.SO].reg.eq(sobit)
                    cabit = xer[XER_bits['CA']].asint()
                    ca32bit = xer[XER_bits['CA32']].asint()
                    yield xregs.regs[xregs.CA].reg.eq(Cat(cabit, ca32bit))
                    ovbit = xer[XER_bits['OV']].asint()
                    ov32bit = xer[XER_bits['OV32']].asint()
                    yield xregs.regs[xregs.OV].reg.eq(Cat(ovbit, ov32bit))
                else:
                    yield xregs.regs[xregs.SO].reg.eq(0)
                    yield xregs.regs[xregs.OV].reg.eq(0)
                    yield xregs.regs[xregs.CA].reg.eq(0)

                index = sim.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("0x{:X}".format(ins & 0xffffffff))
                    print(code)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield ivalid_i.eq(1)
                    yield Settle()
                    #fn_unit = yield pdecode2.e.fn_unit
                    #fuval = self.funit.value
                    #self.assertEqual(fn_unit & fuval, fuval)

                    # set operand and get inputs
                    yield from set_issue(core, pdecode2, sim)
                    yield Settle()

                    yield from wait_for_busy_clear(core)
                    yield ivalid_i.eq(0)
                    yield

                    print ("sim", code)
                    # call simulated operation
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    # int regs
                    intregs = []
                    for i in range(32):
                        rval = yield core.regs.int.regs[i].reg
                        intregs.append(rval)
                    print ("int regs", list(map(hex, intregs)))
                    for i in range(32):
                        simregval = sim.gpr[i].asint()
                        self.assertEqual(simregval, intregs[i],
                            "int reg %d not equal %s" % (i, repr(code)))

                    # CRs
                    crregs = []
                    for i in range(8):
                        rval = yield core.regs.cr.regs[i].reg
                        crregs.append(rval)
                    print ("cr regs", list(map(hex, crregs)))
                    print ("sim cr reg", hex(cr))
                    for i in range(8):
                        rval = crregs[i]
                        cri = sim.crl[7-i].get_range().value
                        print ("cr reg", i, hex(cri), i, hex(rval))
                        # XXX https://bugs.libre-soc.org/show_bug.cgi?id=363
                        self.assertEqual(cri, rval,
                            "cr reg %d not equal %s" % (i, repr(code)))

                    # XER
                    so = yield xregs.regs[xregs.SO].reg
                    ov = yield xregs.regs[xregs.OV].reg
                    ca = yield xregs.regs[xregs.CA].reg

                    e_so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                    e_ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                    e_ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                    e_ca = 1 if sim.spr['XER'][XER_bits['CA']] else 0
                    e_ca32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0

                    e_ov = e_ov | (e_ov32<<1)
                    e_ca = e_ca | (e_ca32<<1)

                    self.assertEqual(e_so, so,
                            "so not equal %s" % (repr(code)))
                    self.assertEqual(e_ov, ov,
                            "ov not equal %s" % (repr(code)))
                    self.assertEqual(e_ca, ca,
                            "ca not equal %s" % (repr(code)))

        sim.add_sync_process(process)
        with sim.write_vcd("core_simulator.vcd", "core_simulator.gtkw",
                            traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    #suite.addTest(TestRunner(CRTestCase.test_data))
    #suite.addTest(TestRunner(ShiftRotTestCase.test_data))
    #suite.addTest(TestRunner(LogicalTestCase.test_data))
    suite.addTest(TestRunner(ALUTestCase.test_data))
    #suite.addTest(TestRunner(BranchTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)

