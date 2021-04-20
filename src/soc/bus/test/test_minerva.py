from soc.bus.sram import SRAM
from nmigen import Memory, Signal, Module
from soc.minerva.units.loadstore import BareLoadStoreUnit, CachedLoadStoreUnit
from soc.minerva.units.fetch import BareFetchUnit, CachedFetchUnit


class TestSRAMBareLoadStoreUnit(BareLoadStoreUnit):
    def __init__(self, pspec):
        super().__init__(pspec)
        pspec = self.pspecslave
        # small 32-entry Memory
        if (hasattr(pspec, "dmem_test_depth") and
                isinstance(pspec.dmem_test_depth, int)):
            depth = pspec.dmem_test_depth
        else:
            depth = 32
        print("TestSRAMBareLoadStoreUnit depth", depth)

        self.mem = Memory(width=pspec.reg_wid, depth=depth)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        m.submodules.sram = sram = SRAM(memory=self.mem, granularity=8,
                                        features={'cti', 'bte', 'err'})
        dbus = self.slavebus

        # directly connect the wishbone bus of LoadStoreUnitInterface to SRAM
        # note: SRAM is a target (slave), dbus is initiator (master)
        fanouts = ['dat_w', 'sel', 'cyc', 'stb', 'we', 'cti', 'bte']
        fanins = ['dat_r', 'ack', 'err']
        for fanout in fanouts:
            print("fanout", fanout, getattr(sram.bus, fanout).shape(),
                  getattr(dbus, fanout).shape())
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
        for fanin in fanins:
            comb += getattr(dbus, fanin).eq(getattr(sram.bus, fanin))
        # connect address
        comb += sram.bus.adr.eq(dbus.adr)

        return m


class TestSRAMBareFetchUnit(BareFetchUnit):
    def __init__(self, pspec):
        super().__init__(pspec)
        # default: small 32-entry Memory
        if (hasattr(pspec, "imem_test_depth") and
                isinstance(pspec.imem_test_depth, int)):
            depth = pspec.imem_test_depth
        else:
            depth = 32
        print("TestSRAMBareFetchUnit depth", depth)
        self.mem = Memory(width=self.data_wid, depth=depth)

    def _get_memory(self):
        return self.mem

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        m.submodules.sram = sram = SRAM(memory=self.mem, read_only=True,
                                        features={'cti', 'bte', 'err'})
        ibus = self.ibus

        # directly connect the wishbone bus of FetchUnitInterface to SRAM
        # note: SRAM is a target (slave), ibus is initiator (master)
        fanouts = ['dat_w', 'sel', 'cyc', 'stb', 'we', 'cti', 'bte']
        fanins = ['dat_r', 'ack', 'err']
        for fanout in fanouts:
            print("fanout", fanout, getattr(sram.bus, fanout).shape(),
                  getattr(ibus, fanout).shape())
            comb += getattr(sram.bus, fanout).eq(getattr(ibus, fanout))
            comb += getattr(sram.bus, fanout).eq(getattr(ibus, fanout))
        for fanin in fanins:
            comb += getattr(ibus, fanin).eq(getattr(sram.bus, fanin))
        # connect address
        comb += sram.bus.adr.eq(ibus.adr)

        return m
