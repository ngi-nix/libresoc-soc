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

        m.d.comb += [
            mem.rdport.addr.eq(self.x_addr),
            self.m_load_data.eq(mem.rdport.data),

            mem.wrport.addr.eq(self.x_addr),
            mem.wrport.en.eq(Mux(self.x_store, self.x_mask, 0)),
            mem.wrport.data.eq(self.x_store_data)
            ]

        m.d.sync += self.x_valid.eq(self.x_load)

        return m


def write_to_addr(dut, addr, value):
    yield dut.x_addr.eq(addr)
    yield dut.x_store_data.eq(value)
    yield dut.x_store.eq(1)
    yield dut.x_mask.eq(-1)

    yield
    yield dut.x_store.eq(0)
    while (yield dut.x_stall):
        yield

def read_from_addr(dut, addr):
    yield dut.x_addr.eq(addr)
    yield dut.x_load.eq(1)
    yield
    yield dut.x_load.eq(0)
    yield Settle()
    while (yield dut.x_stall):
        yield
    assert (yield dut.x_valid)
    return (yield dut.m_load_data)

if __name__ == '__main__':
    m = Module()
    dut = TestMemLoadStoreUnit(regwid=32, addrwid=4)
    m.submodules.dut = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    def process():

        values = [random.randint(0, (1<<32)-1) for x in range(16)]

        for addr, val in enumerate(values):
            yield from write_to_addr(dut, addr, val)
        for addr, val in enumerate(values):
            x = yield from read_from_addr(dut, addr)
            assert x == val

    sim.add_sync_process(process)
    with sim.write_vcd("lsmem.vcd", "lsmem.gtkw", traces=[]):
        sim.run()
