# experimentation with async clocks, clock domains, and AsyncFFSynchronizer

from nmigen import (Elaboratable, Module, Signal, ClockDomain, DomainRenamer,
                    ResetSignal)
from nmigen.lib.cdc import AsyncFFSynchronizer
from nmigen.back.pysim import Simulator, Delay, Settle, Tick
from nmutil.util import wrap


# simple "tick-driven counter" thing
class Domain1(Elaboratable):
    def __init__(self):
        self.tick = Signal()
        self.tick_clear_wait = Signal()
        self.counter = Signal(64)
        self.rst = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += ResetSignal().eq(self.rst)

        # increments the counter each time "tick" goes HI
        with m.If(self.tick & ~self.tick_clear_wait):
            m.d.sync += self.counter.eq(self.counter + 1)
            m.d.sync += self.tick_clear_wait.eq(1)

        # clears waiting when tick is LO
        with m.If(~self.tick & self.tick_clear_wait):
            m.d.sync += self.tick_clear_wait.eq(0)
        return m

# simple "counter" thing
class Domain2(Elaboratable):
    def __init__(self):
        self.counter = Signal(64)
        self.rst = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += ResetSignal().eq(self.rst)
        m.d.sync += self.counter.eq(self.counter + 1)

        return m


class AsyncThing(Elaboratable):
    def __init__(self):

        self.core_clk = Signal()
        self.core_tick = Signal()

    def elaborate(self, platform):
        m = Module()
        core_sync = ClockDomain("coresync")
        m.domains += core_sync
        comb, sync, coresync = m.d.comb, m.d.sync, m.d.coresync

        self.core2 = core2 = Domain2()
        m.submodules.core2 = DomainRenamer("coresync")(core2)
        m.submodules.core = self.core = core = Domain1()

        comb += core_sync.clk.eq(self.core_clk) # driven externally
        comb += core.rst.eq(ResetSignal())

        m.submodules += AsyncFFSynchronizer(self.core_tick, core.tick,
                                            domain="coresync")

        return m


# loops and displays the counter in the main (sync) clock-driven module
def domain_sim(dut):
    for i in range(50):
        yield Tick("coresync")
        counter = (yield dut.core.counter)
        print ("count i", i, counter)


# fires the manually-driven clock at 1/3 the rate (actually about 1/4)
def async_sim_clk(dut):

    for i in range(100):
        yield dut.core_clk.eq(1)
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")

        # deliberately "unbalance" the duty cycle
        yield dut.core_clk.eq(0)
        yield Tick("sync")
        yield Tick("sync")
        yield Tick("sync")

    counter = yield dut.core2.counter
    print ("async counter", counter)
    assert counter == 100 # same as number of loops


# runs at the *sync* simulation rate but yields *coresync*-sized ticks,
# arbitrarily switching core_tick on and off
# this deliberately does not quite match up with when the *clock* ticks
# (see async_sim_clk above)
#
# experimenting by deleting some of these coresyncs (both the on and off ones)
# does in fact "miss" things.

def async_sim(dut):
    for i in range(5):
        yield dut.core_tick.eq(1)
        yield Tick("coresync")
        yield Tick("coresync")
        yield Tick("coresync")

        # switch off but must wait at least 3 coresync ticks because
        # otherwise the coresync domain that the counter is in might
        # miss it (actually AsyncFFSynchronizer would)
        yield dut.core_tick.eq(0)
        yield Tick("coresync")
        yield Tick("coresync")
        yield Tick("coresync")
        yield Tick("coresync")
        yield Tick("coresync")
        yield Tick("coresync")

if __name__ == '__main__':

    dut = AsyncThing()
    m = Module()
    m.submodules.ast = dut

    sim = Simulator(m)
    sim.add_clock(1e-6, domain="sync")      # standard clock

    # nooo don't do this, it requests that the simulation start driving
    # coresync_clk!  and it's to be *manually* driven by async_sim_clk
    #sim.add_clock(3e-6, domain="coresync")  # manually-driven. 1/3 rate

    sim.add_sync_process(wrap(domain_sim(dut)))
    sim.add_sync_process(wrap(async_sim(dut)), domain="coresync")
    sim.add_sync_process(wrap(async_sim_clk(dut)))

    with sim.write_vcd("async_sim.vcd"):
        sim.run()


