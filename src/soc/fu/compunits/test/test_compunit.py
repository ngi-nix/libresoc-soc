from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import Function
from soc.decoder.isa.all import ISA

from soc.experiment.compalu_multi import find_ok # hack


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


def set_operand(cu, dec2, sim):
    yield from cu.oper_i.eq_from_execute1(dec2.e)
    yield cu.issue_i.eq(1)
    yield
    yield cu.issue_i.eq(0)
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
    def __init__(self, test_data, fukls, iodef, funit):
        super().__init__("run_all")
        self.test_data = test_data
        self.fukls = fukls
        self.iodef = iodef
        self.funit = funit

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        if self.funit == Function.LDST:
            from soc.experiment.l0_cache import TstL0CacheBuffer
            m.submodules.l0 = l0 = TstL0CacheBuffer(n_units=1, regwid=64)
            pi = l0.l0.dports[0].pi
            m.submodules.cu = cu = self.fukls(pi, awid=4)
            m.d.comb += cu.ad.go.eq(cu.ad.rel) # link addr-go direct to rel
        else:
            m.submodules.cu = cu = self.fukls()

        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            yield cu.issue_i.eq(0)
            yield

            for test in self.test_data:
                print(test.name)
                program = test.program
                self.subTest(test.name)
                sim = ISA(pdecode2, test.regs, test.sprs, 0)
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
                    fn_unit = yield pdecode2.e.fn_unit
                    fuval = self.funit.value
                    self.assertEqual(fn_unit & fuval, fuval)

                    # set operand and get inputs
                    yield from set_operand(cu, pdecode2, sim)
                    iname = yield from self.iodef.get_cu_inputs(pdecode2, sim)
                    inp = get_inp_indexed(cu, iname)

                    # reset read-operand mask
                    rdmask = pdecode2.rdflags(cu)
                    #print ("hardcoded rdmask", cu.rdflags(pdecode2.e))
                    #print ("decoder rdmask", rdmask)
                    yield cu.rdmaskn.eq(~rdmask)

                    # reset write-operand mask
                    for idx in range(cu.n_dst):
                        wrok = cu.get_out(idx)
                        fname = find_ok(wrok.fields)
                        yield getattr(wrok, fname).eq(0)

                    yield Settle()

                    # set inputs into CU
                    rd_rel_o = yield cu.rd.rel
                    wr_rel_o = yield cu.wr.rel
                    print ("before inputs, rd_rel, wr_rel: ",
                            bin(rd_rel_o), bin(wr_rel_o))
                    assert wr_rel_o == 0, "wr.rel %s must be zero. "\
                                "previous instr not written all regs\n"\
                                "respec %s" % \
                                (bin(wr_rel_o), cu.rwid[1])
                    yield from set_cu_inputs(cu, inp)
                    yield
                    rd_rel_o = yield cu.rd.rel
                    wr_rel_o = yield cu.wr.rel
                    wrmask = yield cu.wrmask
                    print ("after inputs, rd_rel, wr_rel, wrmask: ",
                            bin(rd_rel_o), bin(wr_rel_o), bin(wrmask))

                    # call simulated operation
                    opname = code.split(' ')[0]
                    yield from sim.call(opname)
                    index = sim.pc.CIA.value//4

                    yield Settle()
                    # get all outputs (one by one, just "because")
                    res = yield from get_cu_outputs(cu, code)

                    yield from self.iodef.check_cu_outputs(res, pdecode2,
                                                            sim, code)

        sim.add_sync_process(process)

        name = self.funit.name.lower()
        with sim.write_vcd("%s_simulator.vcd" % name,
                           "%s_simulator.gtkw" % name,
                            traces=[]):
            sim.run()


