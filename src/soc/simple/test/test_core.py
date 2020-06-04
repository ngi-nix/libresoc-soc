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
from soc.fu.alu.test.test_pipe_caller import TestCase, ALUTestCase, test_data
#from soc.fu.logical.test.test_pipe_caller import LogicalTestCase, test_data


def set_cu_input(cu, idx, data):
    rdop = cu.get_in_name(idx)
    yield cu.src_i[idx].eq(data)
    while True:
        rd_rel_o = yield cu.rd.rel[idx]
        print ("rd_rel %d wait HI" % idx, rd_rel_o, rdop, hex(data))
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
    yield cu.src_i[idx].eq(0)


def get_cu_output(cu, idx, code):
    wrmask = yield cu.wrmask
    wrop = cu.get_out_name(idx)
    wrok = cu.get_out(idx)
    fname = find_ok(wrok.fields)
    wrok = yield getattr(wrok, fname)
    print ("wr_rel mask", repr(code), idx, wrop, bin(wrmask), fname, wrok)
    assert wrmask & (1<<idx), \
            "get_cu_output '%s': mask bit %d not set\n" \
            "write-operand '%s' Data.ok likely not set (%s)" \
            % (code, idx, wrop, hex(wrok))
    while True:
        wr_relall_o = yield cu.wr.rel
        wr_rel_o = yield cu.wr.rel[idx]
        print ("wr_rel %d wait" % idx, hex(wr_relall_o), wr_rel_o)
        if wr_rel_o:
            break
        yield
    yield cu.wr.go[idx].eq(1)
    yield Settle()
    result = yield cu.dest[idx]
    yield
    yield cu.wr.go[idx].eq(0)
    print ("result", repr(code), idx, wrop, wrok, hex(result))
    return result


def set_cu_inputs(cu, inp):
    for idx, data in inp.items():
        yield from set_cu_input(cu, idx, data)


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


def get_cu_outputs(cu, code):
    res = {}
    for i in range(cu.n_dst):
        wr_rel_o = yield cu.wr.rel[i]
        if wr_rel_o:
            result = yield from get_cu_output(cu, i, code)
            wrop = cu.get_out_name(i)
            print ("output", i, wrop, hex(result))
            res[wrop] = result
    return res


def get_inp_indexed(cu, inp):
    res = {}
    for i in range(cu.n_src):
        wrop = cu.get_in_name(i)
        if wrop in inp:
            res[i] = inp[wrop]
    return res


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
                sim = ISA(pdecode2, test.regs, test.sprs, 0)
                gen = program.generate_instructions()
                instructions = list(zip(gen, program.assembly.splitlines()))

                # set up INT regfile, "direct" write (bypass rd/write ports)
                for i in range(32):
                    yield core.regs.int.regs[i].reg.eq(test.regs[i])

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

        sim.add_sync_process(process)
        with sim.write_vcd("core_simulator.vcd", "core_simulator.gtkw",
                            traces=[]):
            sim.run()


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)

