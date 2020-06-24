from soc.minerva.units.loadstore import LoadStoreUnitInterface
from nmigen import Signal, Module, Elaboratable
from soc.experiment.testmem import TestMemory # TODO: replace with TMLSUI

from nmigen.back.pysim import Simulator


class TestMemLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def __init__(self, regwid, addrwid):
        super().__init__()
        self.regwid = regwid
        self.addrwid = addrwid
    def elaborate(self, platform):
        m = Module()

        m.submodules.mem = mem = TestMemory(
            self.regwid, self.addrwid, granularity=self.regwid//8)

        m.d.comb += [
            mem.rdport.addr.eq(self.x_addr),
            self.m_load_data.eq(mem.rdport.data),

            mem.wrport.addr.eq(self.x_addr),
            mem.wrport.en.eq(self.x_store),
            mem.wrport.data.eq(self.x_store_data)
            ]

        m.d.sync += self.x_valid.eq(self.x_load)

        return m


def write_to_addr(dut, addr, value):
    yield dut.x_addr.eq(addr)
    yield dut.x_store_data.eq(value)
    yield dut.x_store.eq(1)

    yield
    yield dut.x_store.eq(0)
    while (yield dut.x_stall):
        yield

if __name__ == '__main__':
    m = Module()
    dut = TestMemLoadStoreUnit(regwid=32, addrwid=4)
    m.submodules.dut = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    def process():

        yield from write_to_addr(dut, 0xa, 0xbeef)
        yield dut.x_addr.eq(0xa)
        yield dut.x_load.eq(1)
        yield
        yield dut.x_load.eq(0)
        #while not (yield dut.x_valid) and (yield dut.x_busy):
            #yield
        yield
        yield

    sim.add_sync_process(process)
    with sim.write_vcd("lsmem.vcd", "lsmem.gtkw", traces=[]):
        sim.run()
