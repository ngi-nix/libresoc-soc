from nmigen import Elaboratable, Memory, Module, Signal
from nmigen.utils import log2_int

from nmigen_soc.wishbone.bus import Interface


__all__ = ["SRAM"]


class SRAM(Elaboratable):
    """SRAM module carrying a volatile memory block (implemented with
    :class:`Memory`) that can be read and write (or only read if the
    SRAM is read-only) through a Wishbone bus.

    If no Wishbone bus is specified during initialisation, this creates
    one whose address width is just enough to fit the whole memory
    (i.e. equals to the log2(memory depth) rounded up), and whose data
    width is equal to the memory width.

    Parameters
    ----------
    memory : :class:`Memory`
        The memory to be accessed via the Wishbone bus.
    read_only : bool
        Whether or not the memory is read-only. Defaults to False.
    bus : :class:`Interface` or None
        The Wishbone bus interface providing access to the read/write
        ports of the memory.  Optional and defaults to None, which
        lets this module to instantiate one as described above, having
        the granularity, features and alignment as specified by their
        corresponding parameters.
    granularity : int or None
        If the Wishbone bus is not specified, this is the granularity
        of the Wishbone bus.  Optional. See :class:`Interface`.
    features : iter(str)
        If the Wishbone bus is not specified, this is the optional signal
        set for the Wishbone bus.  See :class:`Interface`.

    Attributes
    ----------
    memory : :class:`Memory`
        The memory to be accessed via the Wishbone bus.
    bus : :class:`Interface`
        The Wishbone bus interface providing access to the read/write
        ports of the memory.
    """

    def __init__(self, memory, read_only=False, bus=None,
                 granularity=None, features=None):
        if features is None:
            features = frozenset()
        if not isinstance(memory, Memory):
            raise TypeError("Memory {!r} is not a Memory"
                            .format(memory))
        self.memory = memory
        self.read_only = read_only
        if bus is None:
            bus = Interface(addr_width=log2_int(self.memory.depth,
                                                need_pow2=False),
                            data_width=self.memory.width,
                            granularity=granularity,
                            features=features,
                            alignment=0,
                            name=None)
        self.bus = bus
        self.granularity = bus.granularity

    def elaborate(self, platform):
        m = Module()

        if self.memory.width > len(self.bus.dat_r):
            raise NotImplementedError

        # read - this relies on the read port producing data
        # with one clock delay. the "ack" goes out on a sync
        # which matches that
        m.submodules.rdport = rdport = self.memory.read_port()
        m.d.comb += [
            rdport.addr.eq(self.bus.adr[:len(rdport.addr)]),
            self.bus.dat_r.eq(rdport.data)
        ]

        # write
        if not self.read_only:
            m.submodules.wrport = wrport = self.memory.write_port(
                granularity=self.granularity)
            m.d.comb += [
                wrport.addr.eq(self.bus.adr[:len(rdport.addr)]),
                wrport.data.eq(self.bus.dat_w)
            ]
            n_wrport = wrport.en.width
            n_bussel = self.bus.sel.width
            assert n_wrport == n_bussel, "bus enable count %d " \
                    "must match memory wen count %d" % (n_wrport, n_bussel)
            wen = Signal()
            m.d.comb += wen.eq(self.bus.cyc & self.bus.stb & self.bus.we)
            with m.If(wen):
                m.d.comb += wrport.en.eq(self.bus.sel)

        # generate ack (no "pipeline" mode here)
        m.d.sync += self.bus.ack.eq(0)
        with m.If(self.bus.cyc & self.bus.stb & ~self.bus.ack):
            m.d.sync += self.bus.ack.eq(1)

        return m
