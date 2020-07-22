from soc.minerva.units.fetch import FetchUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from nmigen.utils import log2_int
import random
from nmigen.back.pysim import Simulator, Settle
from soc.config.ifetch import ConfigFetchUnit
from collections import namedtuple
from nmigen.cli import rtlil

from soc.config.test.test_loadstore import TestMemPspec

import sys
sys.setrecursionlimit(10**6)


def read_from_addr(dut, addr):
    yield dut.a_pc_i.eq(addr)
    yield dut.a_valid_i.eq(1)
    yield dut.f_valid_i.eq(1)
    yield dut.a_stall_i.eq(1)
    yield
    yield dut.a_stall_i.eq(0)
    yield
    yield Settle()
    while (yield dut.f_busy_o):
        yield
    res = (yield dut.f_instr_o)

    yield dut.a_valid_i.eq(0)
    yield dut.f_valid_i.eq(0)
    yield
    return res


def tst_lsmemtype(ifacetype, sram_depth=32):
    m = Module()
    pspec = TestMemPspec(ldst_ifacetype=ifacetype,
                         imem_ifacetype=ifacetype, addr_wid=64,
                         mask_wid=4,
                         reg_wid=32,
                         imem_test_depth=sram_depth)
    dut = ConfigFetchUnit(pspec).fu
    vl = rtlil.convert(dut, ports=[])  # TODOdut.ports())
    with open("test_fetch_%s.il" % ifacetype, "w") as f:
        f.write(vl)

    m.submodules.dut = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    mem = dut._get_memory()

    def process():

        values = [random.randint(0, (1 << 32)-1) for x in range(16)]
        for addr, val in enumerate(values):
            yield mem._array[addr].eq(val)
        yield Settle()

        for addr, val in enumerate(values):
            x = yield from read_from_addr(dut, addr << 2)
            print("addr, val", addr, hex(val), hex(x))
            assert x == val

    sim.add_sync_process(process)
    with sim.write_vcd("test_fetch_%s.vcd" % ifacetype, traces=[]):
        sim.run()


if __name__ == '__main__':
    tst_lsmemtype('test_bare_wb', sram_depth=32768)
    tst_lsmemtype('testmem')
