from nmigen_soc.wishbone.sram import SRAM
from nmigen import Memory, Signal, Module
from soc.minerva.units.loadstore import BareLoadStoreUnit, CacheLoadStoreUnit


class TestSRAMBareLoadStoreUnit(BareLoadStoreUnit):
    def __init__(self, addr_wid=64, mask_wid=4, data_wid=64):
        super().__init__(addr_wid, mask_wid, data_wid)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.mem = memory = Memory(width=addr_wid, depth=16)
        m.submodules.sram = sram = SRAM(memory=memory, granularity=8,
                                        features=set('cti', 'bte', 'err'))
        dbus = self.dbus

        # directly connect the wishbone bus of LoadStoreUnitInterface to SRAM
        # note: SRAM is a target (slave), dbus is initiator (master)
        fanouts = ['adr', 'dat_w', 'sel', 'cyc', 'stb', 'we', 'cti', 'bte']
        fanins = ['dat_r', 'ack', 'err']
        for fanout in fanouts:
            comb += getattr(sram.bus, fanout).eq(getattr(dbus))
        for fanin in fanins:
            comb += getattr(dbus, fanin).eq(getattr(sram.bus))

