from nmigen_soc.wishbone.sram import SRAM
from nmigen import Memory, Signal, Module
from soc.minerva.units.loadstore import BareLoadStoreUnit, CachedLoadStoreUnit


class TestSRAMBareLoadStoreUnit(BareLoadStoreUnit):
    def __init__(self, addr_wid=64, mask_wid=4, data_wid=64):
        super().__init__(addr_wid, mask_wid, data_wid)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        # small 32-entry Memory
        memory = Memory(width=self.addr_wid, depth=32)
        m.submodules.sram = sram = SRAM(memory=memory, granularity=8,
                                        features={'cti', 'bte', 'err'})
        dbus = self.dbus

        # directly connect the wishbone bus of LoadStoreUnitInterface to SRAM
        # note: SRAM is a target (slave), dbus is initiator (master)
        fanouts = ['adr', 'dat_w', 'sel', 'cyc', 'stb', 'we', 'cti', 'bte']
        fanins = ['dat_r', 'ack', 'err']
        for fanout in fanouts:
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
        for fanin in fanins:
            comb += getattr(dbus, fanin).eq(getattr(sram.bus, fanin))

        return m
