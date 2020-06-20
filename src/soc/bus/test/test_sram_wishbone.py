"""demonstration of nmigen-soc SRAM behind a wishbone bus
Bugs:
* https://bugs.libre-soc.org/show_bug.cgi?id=382
"""
from nmigen_soc.wishbone.sram import SRAM
from nmigen import Memory, Signal, Module

memory = Memory(width=32, depth=16)
sram = SRAM(memory=memory,granularity=8)

# valid wishbone signals include
# sram.bus.adr
# sram.bus.dat_w
# sram.bus.dat_r
# sram.bus.sel
# sram.bus.cyc
# sram.bus.stb
# sram.bus.we
# sram.bus.ack

# setup simulation
from nmigen.back.pysim import Simulator, Delay, Settle
m = Module()
m.submodules.sram = sram
sim = Simulator(m)
sim.add_clock(1e-6)

def print_sig(sig, format=None):
    if format == None:
        print(f"{sig.__repr__()} = {(yield sig)}")
    if format == "h":
        print(f"{sig.__repr__()} = {hex((yield sig))}")

def process():
    # enable necessary signals for write
    for en in range(4):
        yield sram.bus.sel[en].eq(1)
    yield sram.bus.we.eq(1)
    yield sram.bus.cyc.eq(1)
    yield sram.bus.stb.eq(1)

    # put data and address on bus
    yield sram.bus.adr.eq(0x4)
    yield sram.bus.dat_w.eq(0xdeadbeef)
    yield

    # set necessary signal to read bus
    # at address 0
    yield sram.bus.we.eq(0)
    yield sram.bus.adr.eq(0)
    yield sram.bus.cyc.eq(1)
    yield sram.bus.stb.eq(1)
    yield

    # see sync_behaviors.py
    # for why we need Settle()
    # debug print the bus address/data
    yield Settle()
    yield from print_sig(sram.bus.adr)
    yield from print_sig(sram.bus.dat_r, "h")

    # check the result
    data = yield sram.bus.dat_r
    assert data == 0

    # set necessary signal to read bus
    # at address 4
    yield sram.bus.we.eq(0)
    yield sram.bus.adr.eq(0x4)
    yield sram.bus.cyc.eq(1)
    yield sram.bus.stb.eq(1)
    yield

    # see sync_behaviors.py
    # for why we need Settle()
    # debug print the bus address/data
    yield Settle()
    yield from print_sig(sram.bus.adr)
    yield from print_sig(sram.bus.dat_r, "h")

    # check the result
    data = yield sram.bus.dat_r
    assert data == 0xdeadbeef

    # disable signals
    yield sram.bus.cyc.eq(0)
    yield sram.bus.stb.eq(0)
    yield

sim_writer = sim.write_vcd(f"{__file__[:-3]}.vcd")

with sim_writer:
    sim.add_sync_process(process)
    sim.run()
