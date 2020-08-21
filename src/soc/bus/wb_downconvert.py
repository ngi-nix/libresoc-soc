from nmigen import Elaboratable, Module, Signal, Repl, Cat, Mux
from nmigen.utils import log2_int

class WishboneDownConvert(Elaboratable):
    """DownConverter

    This module splits Wishbone accesses from a master interface to a smaller
    slave interface.

    Writes:
        Writes from master are split N writes to the slave. Access
        is acked when the last access is acked by the slave.

    Reads:
        Read from master are split in N reads to the the slave.
        Read data from the slave are cached before being presented,
        concatenated on the last access.

    TODO:
        Manage err signal? (Not implemented since we generally don't
        use it on Migen/MiSoC modules)
    """
    def __init__(self, master, slave):
        self.master = master
        self.slave = slave

    def elaborate(self, platform):

        master = self.master
        slave = self.slave
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        dw_from = len(master.dat_r)
        dw_to = len(slave.dat_w)
        ratio = dw_from//dw_to

        print ("wb downconvert from to ratio", dw_from, dw_to, ratio)

        # # #

        read = Signal()
        write = Signal()

        cached_data = Signal(dw_from)
        shift_reg = Signal(dw_from)

        counter = Signal(log2_int(ratio, False))
        counter_reset = Signal()
        counter_ce = Signal()
        with m.If(counter_reset):
            sync += counter.eq(0)
        with m.Elif(counter_ce):
            sync += counter.eq(counter + 1)

        counter_done = Signal()
        comb += counter_done.eq(counter == ratio-1)

        # Main FSM
        with m.FSM() as fsm:
            with m.State("IDLE"):
                comb += counter_reset.eq(1)
                sync += cached_data.eq(0)
                with m.If(master.stb & master.cyc):
                    with m.If(master.we):
                        m.next = "WRITE"
                    with m.Else():
                        m.next = "READ"

            with m.State("WRITE"):
                comb += write.eq(1)
                comb += slave.we.eq(1)
                comb += slave.cyc.eq(1)
                with m.If(master.stb & master.cyc):
                    comb += slave.stb.eq(1)
                    with m.If(slave.ack):
                        comb += counter_ce.eq(1)
                        with m.If(counter_done):
                            comb += master.ack.eq(1)
                            m.next = "IDLE"
                with m.Elif(~master.cyc):
                    m.next = "IDLE"

            with m.State("READ"):
                comb += read.eq(1)
                comb += slave.cyc.eq(1)
                with m.If(master.stb & master.cyc):
                    comb += slave.stb.eq(1)
                    with m.If(slave.ack):
                        comb += counter_ce.eq(1)
                        with m.If(counter_done):
                            comb += master.ack.eq(1)
                            comb += master.dat_r.eq(shift_reg)
                            m.next = "IDLE"
                with m.Elif(~master.cyc):
                    m.next = "IDLE"

        # Address
        if hasattr(slave, 'cti'):
            with m.If(counter_done):
                comb += slave.cti.eq(7) # indicate end of burst
            with m.Else():
                comb += slave.cti.eq(2)
        comb += slave.adr.eq(Cat(counter, master.adr))

        # write Datapath - select fragments of data, depending on "counter"
        with m.Switch(counter):
            slen = slave.sel.width
            for i in range(ratio):
                with m.Case(i):
                    # select fractions of dat_w and associated "sel" bits
                    print ("sel", i, "from", i*slen, "to", (i+1)*slen)
                    comb += slave.sel.eq(master.sel[i*slen:(i+1)*slen])
                    comb += slave.dat_w.eq(master.dat_w[i*dw_to:(i+1)*dw_to])

        # read Datapath - uses cached_data and master.dat_r as a shift-register.
        # by the time "counter" is done (counter_done) this is complete
        comb += shift_reg.eq(Cat(cached_data[dw_to:], slave.dat_r))
        with m.If(read & counter_ce):
            sync += cached_data.eq(shift_reg)


        return m
