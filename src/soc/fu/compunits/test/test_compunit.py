from nmigen import Module, Signal, ResetSignal
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
    print ("set_cu_inputs", inp)
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
    wrmask = yield cu.wrmask
    print ("get_cu_outputs", cu.n_dst, wrmask)
    if not wrmask: # no point waiting (however really should doublecheck wr.rel)
        return {}
    # wait for at least one result
    while True:
        wr_rel_o = yield cu.wr.rel
        if wr_rel_o:
            break
        yield
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

def get_l0_mem(l0): # BLECH!
    if hasattr(l0.pimem, 'lsui'):
        return l0.pimem.lsui.mem
    return l0.pimem.mem.mem

def setup_test_memory(l0, sim):
    mem = get_l0_mem(l0)
    print ("before, init mem", mem.depth, mem.width, mem)
    for i in range(mem.depth):
        data = sim.mem.ld(i*8, 8, False)
        print ("init ", i, hex(data))
        yield mem._array[i].eq(data)
    yield Settle()
    for k, v in sim.mem.mem.items():
        print ("    %6x %016x" % (k, v))
    print ("before, nmigen mem dump")
    for i in range(mem.depth):
        actual_mem = yield mem._array[i]
        print ("    %6i %016x" % (i, actual_mem))


def dump_sim_memory(dut, l0, sim, code):
    mem = get_l0_mem(l0)
    print ("sim mem dump")
    for k, v in sim.mem.mem.items():
        print ("    %6x %016x" % (k, v))
    print ("nmigen mem dump")
    for i in range(mem.depth):
        actual_mem = yield mem._array[i]
        print ("    %6i %016x" % (i, actual_mem))


def check_sim_memory(dut, l0, sim, code):
    mem = get_l0_mem(l0)

    for i in range(mem.depth):
        expected_mem = sim.mem.ld(i*8, 8, False)
        actual_mem = yield mem._array[i]
        dut.assertEqual(expected_mem, actual_mem,
                "%s %d %x %x" % (code, i,
                                 expected_mem, actual_mem))

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

        # copy of the decoder for simulator
        simdec = create_pdecode()
        simdec2 = PowerDecode2(simdec)
        m.submodules.simdec2 = simdec2 # pain in the neck

        if self.funit == Function.LDST:
            from soc.experiment.l0_cache import TstL0CacheBuffer
            m.submodules.l0 = l0 = TstL0CacheBuffer(n_units=1, regwid=64,
                                                    addrwid=3,
                                                    ifacetype='test_bare_wb')
            pi = l0.l0.dports[0]
            m.submodules.cu = cu = self.fukls(pi, awid=3)
            m.d.comb += cu.ad.go.eq(cu.ad.rel) # link addr-go direct to rel
            m.d.comb += cu.st.go.eq(cu.st.rel) # link store-go direct to rel
        else:
            m.submodules.cu = cu = self.fukls(0)

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
                print ("test", test.name, test.mem)
                gen = list(program.generate_instructions())
                insncode = program.assembly.splitlines()
                instructions = list(zip(gen, insncode))
                sim = ISA(simdec2, test.regs, test.sprs, test.cr, test.mem,
                          test.msr,
                          initial_insns=gen, respect_pc=False,
                          disassembly=insncode)

                # initialise memory
                if self.funit == Function.LDST:
                    yield from setup_test_memory(l0, sim)

                index = sim.pc.CIA.value//4
                while True:
                    try:
                        yield from sim.setup_one()
                    except KeyError: # indicates instruction not in imem: stop
                        break
                    yield Settle()
                    ins, code = instructions[index]
                    print(index, code)

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(0)  # little / big?
                    yield instruction.eq(ins)          # raw binary instr.
                    yield Settle()
                    fn_unit = yield pdecode2.e.do.fn_unit
                    fuval = self.funit.value
                    self.assertEqual(fn_unit & fuval, fuval)

                    # set operand and get inputs
                    yield from set_operand(cu, pdecode2, sim)
                    yield Settle()
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
                    rd_rel_o = yield cu.rd.rel
                    wr_rel_o = yield cu.wr.rel
                    wrmask = yield cu.wrmask
                    print ("after inputs, rd_rel, wr_rel, wrmask: ",
                            bin(rd_rel_o), bin(wr_rel_o), bin(wrmask))

                    # call simulated operation
                    yield from sim.execute_one()
                    yield Settle()
                    index = sim.pc.CIA.value//4

                    # get all outputs (one by one, just "because")
                    res = yield from get_cu_outputs(cu, code)
                    wrmask = yield cu.wrmask
                    rd_rel_o = yield cu.rd.rel
                    wr_rel_o = yield cu.wr.rel
                    print ("after got outputs, rd_rel, wr_rel, wrmask: ",
                            bin(rd_rel_o), bin(wr_rel_o), bin(wrmask))

                    # wait for busy to go low
                    while True:
                        busy_o = yield cu.busy_o
                        print ("busy", busy_o)
                        if not busy_o:
                            break
                        yield

                    if self.funit == Function.LDST:
                        yield from dump_sim_memory(self, l0, sim, code)

                    yield from self.iodef.check_cu_outputs(res, pdecode2,
                                                            sim, code)

                    # sigh.  hard-coded.  test memory
                    if self.funit == Function.LDST:
                        yield from check_sim_memory(self, l0, sim, code)


        sim.add_sync_process(process)

        name = self.funit.name.lower()
        with sim.write_vcd("%s_simulator.vcd" % name,
                           "%s_simulator.gtkw" % name,
                            traces=[]):
            sim.run()


