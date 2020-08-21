from soc.minerva.units.loadstore import LoadStoreUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from nmigen.utils import log2_int
import random
from nmigen.back.pysim import Simulator, Settle
from soc.config.loadstore import ConfigLoadStoreUnit
from collections import namedtuple
from nmigen.cli import rtlil
from unittest.mock import Mock

TestMemPspec = Mock  # might as well use Mock, it does the job


def write_to_addr(dut, addr, value):
    yield dut.x_addr_i.eq(addr)
    yield dut.x_st_data_i.eq(value)
    yield dut.x_st_i.eq(1)
    yield dut.x_mask_i.eq(-1)
    yield dut.x_valid_i.eq(1)
    yield dut.x_stall_i.eq(1)
    yield dut.m_valid_i.eq(1)
    yield
    yield

    yield dut.x_stall_i.eq(0)
    yield
    yield
    yield dut.x_st_i.eq(0)
    while (yield dut.x_busy_o):
        yield


def read_from_addr(dut, addr):
    yield dut.x_addr_i.eq(addr)
    yield dut.x_ld_i.eq(1)
    yield dut.x_valid_i.eq(1)
    yield dut.x_stall_i.eq(1)
    yield
    yield dut.x_stall_i.eq(0)
    yield
    yield dut.x_ld_i.eq(0)
    yield Settle()
    while (yield dut.x_busy_o):
        yield
    assert (yield dut.x_valid_i)
    return (yield dut.m_ld_data_o)


def write_byte(dut, addr, val):
    offset = addr & 0x3
    yield dut.x_addr_i.eq(addr)
    yield dut.x_st_data_i.eq(val << (offset * 8))
    yield dut.x_st_i.eq(1)
    yield dut.x_mask_i.eq(1 << offset)
    print("write_byte", addr, bin(1 << offset), hex(val << (offset*8)))
    yield dut.x_valid_i.eq(1)
    yield dut.m_valid_i.eq(1)

    yield
    yield dut.x_st_i.eq(0)
    while (yield dut.x_busy_o):
        yield


def read_byte(dut, addr):
    offset = addr & 0x3
    yield dut.x_addr_i.eq(addr)
    yield dut.x_ld_i.eq(1)
    yield dut.x_valid_i.eq(1)
    yield
    yield dut.x_ld_i.eq(0)
    yield Settle()
    while (yield dut.x_busy_o):
        yield
    assert (yield dut.x_valid_i)
    val = (yield dut.m_ld_data_o)
    print("read_byte", addr, offset, hex(val))
    return (val >> (offset * 8)) & 0xff


def tst_lsmemtype(ifacetype):
    m = Module()
    pspec = TestMemPspec(ldst_ifacetype=ifacetype,
                         imem_ifacetype='', addr_wid=64,
                         mask_wid=4,
                         wb_data_wid=16,
                         reg_wid=32)
    dut = ConfigLoadStoreUnit(pspec).lsi
    vl = rtlil.convert(dut, ports=[])  # TODOdut.ports())
    with open("test_loadstore_%s.il" % ifacetype, "w") as f:
        f.write(vl)

    m.submodules.dut = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    def process():

        values = [random.randint(0, 255) for x in range(0)]
        for addr, val in enumerate(values):
            yield from write_byte(dut, addr, val)
            x = yield from read_from_addr(dut, addr << 2)
            print("addr, val", addr, hex(val), hex(x))
            x = yield from read_byte(dut, addr)
            print("addr, val", addr, hex(val), hex(x))
            assert x == val

        values = [random.randint(0, (1 << 32)-1) for x in range(16)]

        for addr, val in enumerate(values):
            yield from write_to_addr(dut, addr << 2, val)
            x = yield from read_from_addr(dut, addr << 2)
            print("addr, val", addr, hex(val), hex(x))
            assert x == val

    sim.add_sync_process(process)
    with sim.write_vcd("test_loadstore_%s.vcd" % ifacetype, traces=[]):
        sim.run()


if __name__ == '__main__':
    tst_lsmemtype('test_bare_wb')
    tst_lsmemtype('testmem')
