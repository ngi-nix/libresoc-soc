"""demonstration of nmigen-soc SRAM behind a wishbone bus and a downconverter
"""
from nmigen_soc.wishbone.bus import Interface
from soc.bus.sram import SRAM
from nmigen import Memory, Signal, Module
from nmigen.utils import log2_int
from soc.bus.wb_downconvert import WishboneDownConvert

# memory
memory = Memory(width=32, depth=32)
sram = SRAM(memory=memory, granularity=16)

# interface for converter
cvtbus = Interface(addr_width=log2_int(memory.depth//2, need_pow2=False),
                data_width=memory.width*2,
                features={'cti'},
                granularity=16)

# actual converter
downcvt = WishboneDownConvert(cvtbus, sram.bus)
bus = cvtbus

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
m.submodules.downcvt = downcvt
sim = Simulator(m)
sim.add_clock(1e-6)

def print_sig(sig, format=None):
    if format == None:
        print(f"{sig.__repr__()} = {(yield sig)}")
    if format == "h":
        print(f"{sig.__repr__()} = {hex((yield sig))}")

def process():

    test_data = 0xdeadbeef12345678

    # enable necessary signals for write
    for en in range(4):
        yield bus.sel[en].eq(1)
    yield bus.we.eq(1)
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)

    # put data and address on bus
    yield bus.adr.eq(0x4)
    yield bus.dat_w.eq(test_data)
    yield

    while True:
        ack = yield bus.ack
        if ack:
            break
        yield
    yield bus.cyc.eq(0)
    yield bus.stb.eq(0)
    yield bus.adr.eq(0)
    yield bus.dat_w.eq(0)


    # set necessary signal to read bus
    # at address 0
    yield bus.we.eq(0)
    yield bus.adr.eq(0)
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)
    yield

    while True:
        ack = yield bus.ack
        if ack:
            break
        yield

    # see sync_behaviors.py
    # for why we need Settle()
    # debug print the bus address/data
    yield Settle()
    yield from print_sig(bus.adr)
    yield from print_sig(bus.dat_r, "h")

    # check the result
    data = yield bus.dat_r
    assert data == 0

    # set necessary signal to read bus
    # at address 4
    yield bus.we.eq(0)
    yield bus.adr.eq(0x4)
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)
    yield

    while True:
        ack = yield bus.ack
        if ack:
            break
        yield

    data = yield bus.dat_r
    print ("data", hex(data))

    yield from print_sig(bus.adr)
    yield from print_sig(bus.dat_r, "h")

    # check the result
    assert data == test_data, "data != %x %16x" % (test_data, data)

    # disable signals
    yield bus.adr.eq(0)
    yield bus.cyc.eq(0)
    yield bus.stb.eq(0)
    yield

sim_writer = sim.write_vcd(f"{__file__[:-3]}.vcd")

with sim_writer:
    sim.add_sync_process(process)
    sim.run()
