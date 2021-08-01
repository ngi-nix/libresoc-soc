"""simple core test

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""
from nmigen import Module, Signal, Cat
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from openpower.decoder.isa.caller import special_sprs
from openpower.decoder.power_decoder import create_pdecode
from openpower.decoder.power_decoder2 import PowerDecode2
from openpower.decoder.selectable_int import SelectableInt
from openpower.decoder.isa.all import ISA

# note that using SPRreduced has to be done to match the
# PowerDecoder2 SPR map
from openpower.decoder.power_enums import SPRreduced as SPR
from openpower.decoder.power_enums import spr_dict, Function, XER_bits
from soc.config.test.test_loadstore import TestMemPspec
from openpower.endian import bigendian

from soc.simple.core import NonProductionCore
from soc.experiment.compalu_multi import find_ok  # hack

from soc.fu.compunits.test.test_compunit import (setup_tst_memory,
                                                 check_sim_memory)

# test with ALU data and Logical data
from soc.fu.alu.test.test_pipe_caller import ALUTestCase
from soc.fu.logical.test.test_pipe_caller import LogicalTestCase
from soc.fu.shift_rot.test.test_pipe_caller import ShiftRotTestCase
from soc.fu.cr.test.test_pipe_caller import CRTestCase
from soc.fu.branch.test.test_pipe_caller import BranchTestCase
from soc.fu.ldst.test.test_pipe_caller import LDSTTestCase
from openpower.util import spr_to_fast_reg

# list of SPRs that are controlled and managed by the MMU
mmu_sprs = ["PRTBL", "DSISR", "DAR", "PIDR"]

def set_mmu_spr(name, i, val, core): #important keep pep8 formatting
        fsm = core.fus.get_fu("mmu0").alu
        yield fsm.mmu.l_in.mtspr.eq(1)
        yield fsm.mmu.l_in.sprn.eq(i)
        yield fsm.mmu.l_in.rs.eq(val)
        yield
        yield fsm.mmu.l_in.mtspr.eq(0)
        print("mmu_spr was updated")

def setup_regs(pdecode2, core, test):

    # set up INT regfile, "direct" write (bypass rd/write ports)
    intregs = core.regs.int
    for i in range(32):
        if intregs.unary:
            yield intregs.regs[i].reg.eq(test.regs[i])
        else:
            yield intregs.memory._array[i].eq(test.regs[i])
    yield Settle()

    # set up CR regfile, "direct" write across all CRs
    cr = test.cr
    crregs = core.regs.cr
    #cr = int('{:32b}'.format(cr)[::-1], 2)
    print("setup cr reg", hex(cr))
    for i in range(8):
        #j = 7-i
        cri = (cr >> (i*4)) & 0xf
        #cri = int('{:04b}'.format(cri)[::-1], 2)
        print("setup cr reg", hex(cri), i,
              crregs.regs[i].reg.shape())
        yield crregs.regs[i].reg.eq(cri)

    # set up XER.  "direct" write (bypass rd/write ports)
    xregs = core.regs.xer
    print("setup sprs", test.sprs)
    xer = None
    if 'XER' in test.sprs:
        xer = test.sprs['XER']
    if 1 in test.sprs:
        xer = test.sprs[1]
    if xer is not None:
        if isinstance(xer, int):
            xer = SelectableInt(xer, 64)
        sobit = xer[XER_bits['SO']].value
        yield xregs.regs[xregs.SO].reg.eq(sobit)
        cabit = xer[XER_bits['CA']].value
        ca32bit = xer[XER_bits['CA32']].value
        yield xregs.regs[xregs.CA].reg.eq(Cat(cabit, ca32bit))
        ovbit = xer[XER_bits['OV']].value
        ov32bit = xer[XER_bits['OV32']].value
        yield xregs.regs[xregs.OV].reg.eq(Cat(ovbit, ov32bit))
        print("setting XER so %d ca %d ca32 %d ov %d ov32 %d" %
              (sobit, cabit, ca32bit, ovbit, ov32bit))
    else:
        yield xregs.regs[xregs.SO].reg.eq(0)
        yield xregs.regs[xregs.OV].reg.eq(0)
        yield xregs.regs[xregs.CA].reg.eq(0)

    # setting both fast and slow SPRs from test data

    fregs = core.regs.fast
    sregs = core.regs.spr
    for sprname, val in test.sprs.items():
        if isinstance(val, SelectableInt):
            val = val.value
        if isinstance(sprname, int):
            sprname = spr_dict[sprname].SPR
        if sprname == 'XER':
            continue
        fast = spr_to_fast_reg(sprname)
        if fast is None:
            # match behaviour of SPRMap in power_decoder2.py
            for i, x in enumerate(SPR):
                if sprname == x.name:
                    print("setting slow SPR %d (%s) to %x" %
                          (i, sprname, val))
                    if not sprname in mmu_sprs:
                        yield sregs.memory._array[i].eq(val)
                    else:
                        yield from set_mmu_spr(sprname, i, val, core)
        else:
            print("setting fast reg %d (%s) to %x" %
                  (fast, sprname, val))
            if fregs.unary:
                rval = fregs.int.regs[fast].reg
            else:
                rval = fregs.memory._array[fast]
            yield rval.eq(val)

    # allow changes to settle before reporting on XER
    yield Settle()

    # XER
    so = yield xregs.regs[xregs.SO].reg
    ov = yield xregs.regs[xregs.OV].reg
    ca = yield xregs.regs[xregs.CA].reg
    oe = yield pdecode2.e.do.oe.oe
    oe_ok = yield pdecode2.e.do.oe.oe_ok

    print("before: so/ov-32/ca-32", so, bin(ov), bin(ca))
    print("oe:", oe, oe_ok)


def check_regs(dut, sim, core, test, code):
    # int regs
    intregs = []
    for i in range(32):
        if core.regs.int.unary:
            rval = yield core.regs.int.regs[i].reg
        else:
            rval = yield core.regs.int.memory._array[i]
        intregs.append(rval)
    print("int regs", list(map(hex, intregs)))
    for i in range(32):
        simregval = sim.gpr[i].asint()
        dut.assertEqual(simregval, intregs[i],
                        "int reg %d not equal %s. got %x expected %x" % \
                            (i, repr(code), simregval, intregs[i]))

    # CRs
    crregs = []
    for i in range(8):
        rval = yield core.regs.cr.regs[i].reg
        crregs.append(rval)
    print("cr regs", list(map(hex, crregs)))
    for i in range(8):
        rval = crregs[i]
        cri = sim.crl[7-i].get_range().value
        print("cr reg", i, hex(cri), i, hex(rval))
        # XXX https://bugs.libre-soc.org/show_bug.cgi?id=363
        dut.assertEqual(cri, rval,
                        "cr reg %d not equal %s" % (i, repr(code)))

    # XER
    xregs = core.regs.xer
    so = yield xregs.regs[xregs.SO].reg
    ov = yield xregs.regs[xregs.OV].reg
    ca = yield xregs.regs[xregs.CA].reg

    print("sim SO", sim.spr['XER'][XER_bits['SO']])
    e_so = sim.spr['XER'][XER_bits['SO']].value
    e_ov = sim.spr['XER'][XER_bits['OV']].value
    e_ov32 = sim.spr['XER'][XER_bits['OV32']].value
    e_ca = sim.spr['XER'][XER_bits['CA']].value
    e_ca32 = sim.spr['XER'][XER_bits['CA32']].value

    e_ov = e_ov | (e_ov32 << 1)
    e_ca = e_ca | (e_ca32 << 1)

    print("after: so/ov-32/ca-32", so, bin(ov), bin(ca))
    dut.assertEqual(e_so, so, "so mismatch %s" % (repr(code)))
    dut.assertEqual(e_ov, ov, "ov mismatch %s" % (repr(code)))
    dut.assertEqual(e_ca, ca, "ca mismatch %s" % (repr(code)))

    # Check the PC as well
    state = core.regs.state
    pc = yield state.r_ports['cia'].data_o
    e_pc = sim.pc.CIA.value
    dut.assertEqual(e_pc, pc)


def wait_for_busy_hi(cu):
    while True:
        busy_o = yield cu.busy_o
        terminate_o = yield cu.core_terminate_o
        if busy_o:
            print("busy/terminate:", busy_o, terminate_o)
            break
        print("!busy", busy_o, terminate_o)
        yield


def set_issue(core, dec2, sim):
    yield core.issue_i.eq(1)
    yield
    yield core.issue_i.eq(0)
    yield from wait_for_busy_hi(core)


def wait_for_busy_clear(cu):
    while True:
        busy_o = yield cu.busy_o
        terminate_o = yield cu.core_terminate_o
        if not busy_o:
            print("busy/terminate:", busy_o, terminate_o)
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

        pspec = TestMemPspec(ldst_ifacetype='testpi',
                             imem_ifacetype='',
                             addr_wid=48,
                             mask_wid=8,
                             reg_wid=64)

        m.submodules.core = core = NonProductionCore(pspec)
        pdecode2 = core.pdecode2
        l0 = core.l0

        comb += core.raw_opcode_i.eq(instruction)
        comb += core.ivalid_i.eq(ivalid_i)

        # temporary hack: says "go" immediately for both address gen and ST
        ldst = core.fus.fus['ldst0']
        m.d.comb += ldst.ad.go.eq(ldst.ad.rel)  # link addr-go direct to rel
        m.d.comb += ldst.st.go.eq(ldst.st.rel)  # link store-go direct to rel

        # nmigen Simulation
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
                          test.msr,
                          bigendian=bigendian)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                yield from setup_tst_memory(l0, sim)
                yield from setup_regs(core, test)

                index = sim.pc.CIA.value//4
                while index < len(instructions):
                    ins, code = instructions[index]

                    print("instruction: 0x{:X}".format(ins & 0xffffffff))
                    print(code)

                    # ask the decoder to decode this binary data (endian'd)
                    yield core.bigendian_i.eq(bigendian)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield ivalid_i.eq(1)
                    yield Settle()
                    # fn_unit = yield pdecode2.e.fn_unit
                    #fuval = self.funit.value
                    #self.assertEqual(fn_unit & fuval, fuval)

                    # set operand and get inputs
                    yield from set_issue(core, pdecode2, sim)
                    yield Settle()

                    yield from wait_for_busy_clear(core)
                    yield ivalid_i.eq(0)
                    yield

                    print("sim", code)
                    # call simulated operation
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    # register check
                    yield from check_regs(self, sim, core, test, code)

                    # Memory check
                    yield from check_sim_memory(self, l0, sim, code)

        sim.add_sync_process(process)
        with sim.write_vcd("core_simulator.vcd", "core_simulator.gtkw",
                           traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(LDSTTestCase().test_data))
    suite.addTest(TestRunner(CRTestCase().test_data))
    suite.addTest(TestRunner(ShiftRotTestCase().test_data))
    suite.addTest(TestRunner(LogicalTestCase().test_data))
    suite.addTest(TestRunner(ALUTestCase().test_data))
    suite.addTest(TestRunner(BranchTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
