from soc.minerva.units.loadstore import LoadStoreUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from soc.experiment.testmem import TestMemory # TODO: replace with TMLSUI
import random

from nmigen.back.pysim import Simulator, Settle


class TestMemLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def __init__(self, regwid, addrwid):
        super().__init__()
        self.regwid = regwid
        self.addrwid = addrwid
    def elaborate(self, platform):
        m = Module()


        m.submodules.mem = mem = TestMemory(
            self.regwid, self.addrwid, granularity=8)

        do_load = Signal()  # set when doing a load while valid and not stalled
        do_store = Signal() # set when doing a store while valid and not stalled

        m.d.comb += [
            do_load.eq(self.x_load & (self.x_valid & ~self.x_stall)),
            do_store.eq(self.x_store & (self.x_valid & ~self.x_stall)),
            ]
        m.d.comb += [
            mem.rdport.addr.eq(self.x_addr[2:]),
            self.m_load_data.eq(mem.rdport.data),

            mem.wrport.addr.eq(self.x_addr[2:]),
            mem.wrport.en.eq(Mux(do_store, self.x_mask, 0)),
            mem.wrport.data.eq(self.x_store_data)
            ]

        return m


def write_to_addr(dut, addr, value):
    yield dut.x_addr.eq(addr)
    yield dut.x_store_data.eq(value)
    yield dut.x_store.eq(1)
    yield dut.x_mask.eq(-1)
    yield dut.x_valid.eq(1)
    yield dut.x_stall.eq(1)
    yield
    yield
    
    yield dut.x_stall.eq(0)
    yield
    yield dut.x_store.eq(0)
    while (yield dut.x_stall):
        yield

def read_from_addr(dut, addr):
    yield dut.x_addr.eq(addr)
    yield dut.x_load.eq(1)
    yield dut.x_valid.eq(1)
    yield dut.x_stall.eq(1)
    yield
    yield dut.x_stall.eq(0)
    yield
    yield dut.x_load.eq(0)
    yield Settle()
    while (yield dut.x_stall):
        yield
    assert (yield dut.x_valid)
    return (yield dut.m_load_data)

def write_byte(dut, addr, val):
    offset = addr & 0x3
    yield dut.x_addr.eq(addr)
    yield dut.x_store.eq(1)
    yield dut.x_store_data.eq(val << (offset * 8))
    yield dut.x_mask.eq(1 << offset)
    yield dut.x_valid.eq(1)

    yield
    yield dut.x_store.eq(0)
    while (yield dut.x_stall):
        yield

def read_byte(dut, addr):
    offset = addr & 0x3
    yield dut.x_addr.eq(addr)
    yield dut.x_load.eq(1)
    yield dut.x_valid.eq(1)
    yield
    yield dut.x_load.eq(0)
    yield Settle()
    while (yield dut.x_stall):
        yield
    assert (yield dut.x_valid)
    val = (yield dut.m_load_data)
    return (val >> (offset * 8)) & 0xff

if __name__ == '__main__':
    m = Module()
    dut = TestMemLoadStoreUnit(regwid=32, addrwid=4)
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
    with sim.write_vcd("lsmem.vcd", "lsmem.gtkw", traces=[]):
        sim.run()
