from nmigen import Array, Elaboratable, Module, Record, Signal
from nmigen.hdl.rec import DIR_FANIN, DIR_FANOUT, DIR_NONE
from nmigen.lib.coding import PriorityEncoder
from nmigen.utils import log2_int


__all__ = ["Cycle", "make_wb_layout", "WishboneArbiter"]


class Cycle:
    CLASSIC   = 0
    CONSTANT  = 1
    INCREMENT = 2
    END       = 7


def make_wb_layout(spec, cti=True):
    addr_wid, mask_wid, data_wid = spec.addr_wid, spec.mask_wid, spec.reg_wid
    adr_lsbs = log2_int(mask_wid) # LSBs of addr covered by mask
    badwid = spec.addr_wid-adr_lsbs    # MSBs (not covered by mask)

    res = [
    ("adr",   badwid  , DIR_FANOUT),
    ("dat_w", data_wid, DIR_FANOUT),
    ("dat_r", data_wid, DIR_FANIN),
    ("sel",   mask_wid, DIR_FANOUT),
    ("cyc",           1, DIR_FANOUT),
    ("stb",           1, DIR_FANOUT),
    ("ack",           1, DIR_FANIN),
    ("we",            1, DIR_FANOUT),
    ("err",           1, DIR_FANIN)
    ]
    if not cti:
        return res
    return res + [
        ("cti",           3, DIR_FANOUT),
        ("bte",           2, DIR_FANOUT),
    ]


class WishboneArbiter(Elaboratable):
    def __init__(self, pspec):
        self.bus = Record(make_wb_layout(pspec))
        self._port_map = dict()

    def port(self, priority):
        if not isinstance(priority, int) or priority < 0:
            raise TypeError("Priority must be a non-negative "\
                            "integer, not '{!r}'" .format(priority))
        if priority in self._port_map:
            raise ValueError("Conflicting priority: '{!r}'".format(priority))
        port = self._port_map[priority] = Record.like(self.bus)
        return port

    def elaborate(self, platform):
        m = Module()

        ports = [port for priority, port in sorted(self._port_map.items())]

        for port in ports:
            m.d.comb += port.dat_r.eq(self.bus.dat_r)

        bus_pe = m.submodules.bus_pe = PriorityEncoder(len(ports))
        with m.If(~self.bus.cyc):
            for j, port in enumerate(ports):
                m.d.sync += bus_pe.i[j].eq(port.cyc)

        source = Array(ports)[bus_pe.o]
        m.d.comb += [
            self.bus.adr.eq(source.adr),
            self.bus.dat_w.eq(source.dat_w),
            self.bus.sel.eq(source.sel),
            self.bus.cyc.eq(source.cyc),
            self.bus.stb.eq(source.stb),
            self.bus.we.eq(source.we),
            self.bus.cti.eq(source.cti),
            self.bus.bte.eq(source.bte),
            source.ack.eq(self.bus.ack),
            source.err.eq(self.bus.err)
        ]

        return m
