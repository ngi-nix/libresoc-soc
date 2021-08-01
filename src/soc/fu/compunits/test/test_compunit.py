from nmigen import Module, Signal, ResetSignal, Memory

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from openpower.decoder.power_decoder import create_pdecode
from openpower.decoder.power_decoder2 import PowerDecode2, get_rdflags
from openpower.decoder.power_enums import Function
from openpower.decoder.isa.all import ISA

from soc.experiment.compalu_multi import find_ok  # hack
from soc.config.test.test_loadstore import TestMemPspec


def set_cu_input(cu, idx, data):
    rdop = cu.get_in_name(idx)
    yield cu.src_i[idx].eq(data)
    while True:
        rd_rel_o = yield cu.rd.rel_o[idx]
        print("rd_rel %d wait HI" % idx, rd_rel_o, rdop, hex(data))
        if rd_rel_o:
            break
        yield
    yield cu.rd.go_i[idx].eq(1)
    while True:
        yield
        rd_rel_o = yield cu.rd.rel_o[idx]
        if rd_rel_o:
            break
        print("rd_rel %d wait HI" % idx, rd_rel_o)
        yield
    yield cu.rd.go_i[idx].eq(0)
    yield cu.src_i[idx].eq(0)


def get_cu_output(cu, idx, code):
    wrmask = yield cu.wrmask
    wrop = cu.get_out_name(idx)
    wrok = cu.get_out(idx)
    fname = find_ok(wrok.fields)
    wrok = yield getattr(wrok, fname)
    print("wr_rel mask", repr(code), idx, wrop, bin(wrmask), fname, wrok)
    assert wrmask & (1 << idx), \
        "get_cu_output '%s': mask bit %d not set\n" \
        "write-operand '%s' Data.ok likely not set (%s)" \
        % (code, idx, wrop, hex(wrok))
    while True:
        wr_relall_o = yield cu.wr.rel_o
        wr_rel_o = yield cu.wr.rel_o[idx]
        print("wr_rel %d wait" % idx, hex(wr_relall_o), wr_rel_o)
        if wr_rel_o:
            break
        yield
    yield cu.wr.go_i[idx].eq(1)
    yield Settle()
    result = yield cu.dest[idx]
    yield
    yield cu.wr.go_i[idx].eq(0)
    print("result", repr(code), idx, wrop, wrok, hex(result))

    return result


def set_cu_inputs(cu, inp):
    print("set_cu_inputs", inp)
    for idx, data in inp.items():
        yield from set_cu_input(cu, idx, data)
    # gets out of sync when checking busy if there is no wait, here.
    if len(inp) == 0:
        yield  # wait one cycle


def set_operand(cu, dec2, sim):
    yield from cu.oper_i.eq_from_execute1(dec2.do)
    yield cu.issue_i.eq(1)
    yield
    yield cu.issue_i.eq(0)
    yield


def get_cu_outputs(cu, code):
    res = {}
    # wait for pipeline to indicate valid.  this because for long
    # pipelines (or FSMs) the write mask is only valid at that time.
    if hasattr(cu, "alu"): # ALU CompUnits
        while True:
            valid_o = yield cu.alu.n.valid_o
            if valid_o:
                break
            yield
    else: # LDST CompUnit
        # not a lot can be done about this - simply wait a few cycles
        for i in range(5):
            yield

    wrmask = yield cu.wrmask
    wr_rel_o = yield cu.wr.rel_o
    print("get_cu_outputs", cu.n_dst, wrmask, wr_rel_o)
    # no point waiting (however really should doublecheck wr.rel)
    if not wrmask:
        return {}
    # wait for at least one result
    while True:
        wr_rel_o = yield cu.wr.rel_o
        if wr_rel_o:
            break
        yield
    for i in range(cu.n_dst):
        wr_rel_o = yield cu.wr.rel_o[i]
        if wr_rel_o:
            result = yield from get_cu_output(cu, i, code)
            wrop = cu.get_out_name(i)
            print("output", i, wrop, hex(result))
            res[wrop] = result
    return res


def get_inp_indexed(cu, inp):
    res = {}
    for i in range(cu.n_src):
        wrop = cu.get_in_name(i)
        if wrop in inp:
            res[i] = inp[wrop]
    return res


def get_l0_mem(l0):  # BLECH! this is awful! hunting around through structures
    if hasattr(l0.pimem, 'lsui'):
        return l0.pimem.lsui.mem
    mem = l0.pimem.mem
    if isinstance(mem, Memory): # euuurg this one is for TestSRAMLoadStore1
        return mem
    return mem.mem


def setup_tst_memory(l0, sim):
    mem = get_l0_mem(l0)
    print("before, init mem", mem.depth, mem.width, mem)
    for i in range(mem.depth):
        data = sim.mem.ld(i*8, 8, False)
        print("init ", i, hex(data))
        yield mem._array[i].eq(data)
    yield Settle()
    for k, v in sim.mem.mem.items():
        print("    %6x %016x" % (k, v))
    print("before, nmigen mem dump")
    for i in range(mem.depth):
        actual_mem = yield mem._array[i]
        print("    %6i %016x" % (i, actual_mem))


def dump_sim_memory(dut, l0, sim, code):
    mem = get_l0_mem(l0)
    print("sim mem dump")
    for k, v in sim.mem.mem.items():
        print("    %6x %016x" % (k, v))
    print("nmigen mem dump")
    for i in range(mem.depth):
        actual_mem = yield mem._array[i]
        print("    %6i %016x" % (i, actual_mem))


def check_sim_memory(dut, l0, sim, code):
    mem = get_l0_mem(l0)

    for i in range(mem.depth):
        expected_mem = sim.mem.ld(i*8, 8, False)
        actual_mem = yield mem._array[i]
        dut.assertEqual(expected_mem, actual_mem,
                        "%s %d %x %x" % (code, i,
                                         expected_mem, actual_mem))


class TestRunner(FHDLTestCase):
    def __init__(self, test_data, fukls, iodef, funit, bigendian):
        super().__init__("run_all")
        self.test_data = test_data
        self.fukls = fukls
        self.iodef = iodef
        self.funit = funit
        self.bigendian = bigendian

    def execute(self, cu, l0, instruction, pdecode2, simdec2, test):

        program = test.program
        print("test", test.name, test.mem)
        gen = list(program.generate_instructions())
        insncode = program.assembly.splitlines()
        instructions = list(zip(gen, insncode))
        sim = ISA(simdec2, test.regs, test.sprs, test.cr, test.mem,
                  test.msr,
                  initial_insns=gen, respect_pc=True,
                  disassembly=insncode,
                  bigendian=self.bigendian)

        # initialise memory
        if self.funit == Function.LDST:
            yield from setup_tst_memory(l0, sim)

        pc = sim.pc.CIA.value
        index = pc//4
        msr = sim.msr.value
        while True:
            print("instr pc", pc)
            try:
                yield from sim.setup_one()
            except KeyError:  # indicates instruction not in imem: stop
                break
            yield Settle()
            ins, code = instructions[index]
            print("instruction @", index, code)

            # ask the decoder to decode this binary data (endian'd)
            yield pdecode2.dec.bigendian.eq(self.bigendian)  # le / be?
            yield pdecode2.state.msr.eq(msr)  # set MSR "state"
            yield pdecode2.state.pc.eq(pc)  # set PC "state"
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()
            # debugging issue with branch
            if self.funit == Function.BRANCH:
                lk = yield pdecode2.e.do.lk
                fast_out2 = yield pdecode2.e.write_fast2.data
                fast_out2_ok = yield pdecode2.e.write_fast2.ok
                print("lk:", lk, fast_out2, fast_out2_ok)
                op_lk = yield cu.alu.pipe1.p.data_i.ctx.op.lk
                print("op_lk:", op_lk)
                print(dir(cu.alu.pipe1.n.data_o))
            fn_unit = yield pdecode2.e.do.fn_unit
            fuval = self.funit.value
            self.assertEqual(fn_unit & fuval, fuval)

            # set operand and get inputs
            yield from set_operand(cu, pdecode2, sim)
            # reset read-operand mask
            rdmask = get_rdflags(pdecode2.e, cu)
            #print ("hardcoded rdmask", cu.rdflags(pdecode2.e))
            #print ("decoder rdmask", rdmask)
            yield cu.rdmaskn.eq(~rdmask)

            yield Settle()
            iname = yield from self.iodef.get_cu_inputs(pdecode2, sim)
            inp = get_inp_indexed(cu, iname)

            # reset write-operand mask
            for idx in range(cu.n_dst):
                wrok = cu.get_out(idx)
                fname = find_ok(wrok.fields)
                yield getattr(wrok, fname).eq(0)

            yield Settle()

            # set inputs into CU
            rd_rel_o = yield cu.rd.rel_o
            wr_rel_o = yield cu.wr.rel_o
            print("before inputs, rd_rel, wr_rel: ",
                  bin(rd_rel_o), bin(wr_rel_o))
            assert wr_rel_o == 0, "wr.rel %s must be zero. "\
                "previous instr not written all regs\n"\
                "respec %s" % \
                (bin(wr_rel_o), cu.rwid[1])
            yield from set_cu_inputs(cu, inp)
            rd_rel_o = yield cu.rd.rel_o
            wr_rel_o = yield cu.wr.rel_o
            wrmask = yield cu.wrmask
            print("after inputs, rd_rel, wr_rel, wrmask: ",
                  bin(rd_rel_o), bin(wr_rel_o), bin(wrmask))

            # call simulated operation
            yield from sim.execute_one()
            yield Settle()
            pc = sim.pc.CIA.value
            index = pc//4
            msr = sim.msr.value

            # get all outputs (one by one, just "because")
            res = yield from get_cu_outputs(cu, code)
            wrmask = yield cu.wrmask
            rd_rel_o = yield cu.rd.rel_o
            wr_rel_o = yield cu.wr.rel_o
            print("after got outputs, rd_rel, wr_rel, wrmask: ",
                  bin(rd_rel_o), bin(wr_rel_o), bin(wrmask))

            # wait for busy to go low
            while True:
                busy_o = yield cu.busy_o
                print("busy", busy_o)
                if not busy_o:
                    break
                yield

            # reset read-mask.  IMPORTANT when there are no operands
            yield cu.rdmaskn.eq(0)
            yield

            # debugging issue with branch
            if self.funit == Function.BRANCH:
                lr = yield cu.alu.pipe1.n.data_o.lr.data
                lr_ok = yield cu.alu.pipe1.n.data_o.lr.ok
                print("lr:", hex(lr), lr_ok)

            if self.funit == Function.LDST:
                yield from dump_sim_memory(self, l0, sim, code)

            # sigh.  hard-coded.  test memory
            if self.funit == Function.LDST:
                yield from check_sim_memory(self, l0, sim, code)
                yield from self.iodef.check_cu_outputs(res, pdecode2,
                                                       sim, cu,
                                                       code)
            else:
                yield from self.iodef.check_cu_outputs(res, pdecode2,
                                                       sim, cu.alu,
                                                       code)

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()
        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        # copy of the decoder for simulator
        simdec = create_pdecode()
        simdec2 = PowerDecode2(simdec)
        m.submodules.simdec2 = simdec2  # pain in the neck

        if self.funit == Function.LDST:
            from soc.experiment.l0_cache import TstL0CacheBuffer
            pspec = TestMemPspec(ldst_ifacetype='test_bare_wb',
                                 addr_wid=48,
                                 mask_wid=8,
                                 reg_wid=64)
            m.submodules.l0 = l0 = TstL0CacheBuffer(pspec, n_units=1)
            pi = l0.l0.dports[0]
            m.submodules.cu = cu = self.fukls(pi, idx=0, awid=3)
            m.d.comb += cu.ad.go_i.eq(cu.ad.rel_o)  # link addr direct to rel
            m.d.comb += cu.st.go_i.eq(cu.st.rel_o)  # link store direct to rel
        else:
            m.submodules.cu = cu = self.fukls(0)
            l0 = None

        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            yield cu.issue_i.eq(0)
            yield

            for test in self.test_data:
                print(test.name)
                with self.subTest(test.name):
                    yield from self.execute(cu, l0, instruction,
                                            pdecode2, simdec2,
                                            test)

        sim.add_sync_process(process)

        name = self.funit.name.lower()
        with sim.write_vcd("%s_simulator.vcd" % name,
                           traces=[]):
            sim.run()
