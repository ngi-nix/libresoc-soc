from soc.minerva.units.loadstore import LoadStoreUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from nmigen.utils import log2_int
import random
from nmigen.back.pysim import Simulator, Settle
from soc.config.loadstore import ConfigLoadStoreUnit
from collections import namedtuple


def write_to_addr(dut, addr, value):
    yield dut.x_addr_i.eq(addr)
    yield dut.x_st_data_i.eq(value)
    yield dut.x_st_i.eq(1)
    yield dut.x_mask_i.eq(-1)
    yield dut.x_valid_i.eq(1)
    yield dut.x_stall_i.eq(1)
    yield
    yield
    
    yield dut.x_stall_i.eq(0)
    yield
    yield dut.x_st_i.eq(0)
    while (yield dut.x_stall_i):
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
    while (yield dut.x_stall_i):
        yield
    assert (yield dut.x_valid_i)
    return (yield dut.m_ld_data_o)


def write_byte(dut, addr, val):
    offset = addr & 0x3
    yield dut.x_addr_i.eq(addr)
    yield dut.x_st_i.eq(1)
    yield dut.x_st_data_i.eq(val << (offset * 8))
    yield dut.x_mask_i.eq(1 << offset)
    yield dut.x_valid_i.eq(1)

    yield
    yield dut.x_st_i.eq(0)
    while (yield dut.x_stall_i):
        yield


def read_byte(dut, addr):
    offset = addr & 0x3
    yield dut.x_addr_i.eq(addr)
    yield dut.x_ld_i.eq(1)
    yield dut.x_valid_i.eq(1)
    yield
    yield dut.x_ld_i.eq(0)
    yield Settle()
    while (yield dut.x_stall_i):
        yield
    assert (yield dut.x_valid_i)
    val = (yield dut.m_ld_data_o)
    return (val >> (offset * 8)) & 0xff


def tst_lsmemtype(ifacetype):
    m = Module()
    Pspec = namedtuple('Pspec', ['ldst_ifacetype',
                                 'addr_wid', 'mask_wid', 'reg_wid'])
    pspec = Pspec(ldst_ifacetype=ifacetype, addr_wid=64, mask_wid=4, reg_wid=64)
    dut = ConfigLoadStoreUnit(pspec).lsi
    m.submodules.dut = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    def process():

        values = [random.randint(0, (1<<32)-1) for x in range(16)]

        for addr, val in enumerate(values):
            yield from write_to_addr(dut, addr << 2, val)
        for addr, val in enumerate(values):
            x = yield from read_from_addr(dut, addr << 2)
            assert x == val

        values = [random.randint(0, 255) for x in range(16*4)]
        for addr, val in enumerate(values):
            yield from write_byte(dut, addr, val)
        for addr, val in enumerate(values):
            x = yield from read_byte(dut, addr)
            assert x == val

    sim.add_sync_process(process)
    with sim.write_vcd("test_loadstore_%s.vcd" % ifacetype, traces=[]):
        sim.run()

if __name__ == '__main__':
    tst_lsmemtype('testmem')
    tst_lsmemtype('test_bare_wb')
