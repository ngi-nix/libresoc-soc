"""DCache

based on Anton Blanchard microwatt dcache.vhdl

note that the microwatt dcache wishbone interface expects "stall".
for simplicity at the moment this is hard-coded to cyc & ~ack.
see WB4 spec, p84, section 5.2.1

IMPORTANT: for store, the data is sampled the cycle AFTER the "valid"
is raised.  sigh

Links:

* https://libre-soc.org/3d_gpu/architecture/set_associative_cache.jpg
* https://bugs.libre-soc.org/show_bug.cgi?id=469

"""

import sys

from nmutil.gtkw import write_gtkw

sys.setrecursionlimit(1000000)

from enum import Enum, unique

from nmigen import Module, Signal, Elaboratable, Cat, Repl, Array, Const

from copy import deepcopy
from random import randint, seed

from soc.experiment.cache_ram import CacheRam

# for test
from soc.bus.sram import SRAM
from nmigen import Memory
from nmigen.cli import rtlil

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator

from nmutil.util import wrap

from soc.experiment.dcache import DCache


def dcache_load_m(dut, addr, nc=0):
    REF = 1<<8
    CHG = 1<<7
    NC = 1<<5
    PRIV = 1<<3
    RD = 1<<2
    WR = 1<<1
    pte = RD | WR | REF | PRIV
    yield dut.m_in.pte.eq(pte)
    yield dut.m_in.addr.eq(addr)
    yield dut.m_in.valid.eq(1)
    yield
    yield dut.m_in.valid.eq(0)
    while not (yield dut.m_out.done):
        yield
    # yield # data is valid one cycle AFTER valid goes hi? (no it isn't)
    data = yield dut.m_out.data
    return data


def dcache_load(dut, addr, nc=0):
    yield dut.d_in.load.eq(1)
    yield dut.d_in.nc.eq(nc)
    yield dut.d_in.addr.eq(addr)
    yield dut.d_in.byte_sel.eq(~0)
    yield dut.d_in.valid.eq(1)
    yield
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.byte_sel.eq(0)
    while not (yield dut.d_out.valid):
        yield
    # yield # data is valid one cycle AFTER valid goes hi? (no it isn't)
    data = yield dut.d_out.data
    return data


def dcache_store(dut, addr, data, nc=0):
    yield dut.d_in.load.eq(0)
    yield dut.d_in.nc.eq(nc)
    yield dut.d_in.byte_sel.eq(~0)
    yield dut.d_in.addr.eq(addr)
    yield dut.d_in.valid.eq(1)
    yield
    yield dut.d_in.data.eq(data)    # leave set, but the cycle AFTER
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.byte_sel.eq(0)
    while not (yield dut.d_out.valid):
        yield


def dcache_random_sim(dut, mem, nc=0):

    # start copy of mem
    sim_mem = deepcopy(mem)
    memsize = len(sim_mem)
    print ("mem len", memsize)

    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.priv_mode.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield

    print ()

    #for i in range(1024):
    #    sim_mem[i] = i

    for i in range(1024):
        addr = randint(0, memsize-1)
        data = randint(0, (1<<64)-1)
        sim_mem[addr] = data
        row = addr
        addr *= 8

        print ("random testing %d 0x%x row %d data 0x%x" % (i, addr, row, data))

        yield from dcache_load(dut, addr, nc)
        yield from dcache_store(dut, addr, data, nc)

        addr = randint(0, memsize-1)
        sim_data = sim_mem[addr]
        row = addr
        addr *= 8

        print ("    load 0x%x row %d expect data 0x%x" % (addr, row, sim_data))
        data = yield from dcache_load(dut, addr, nc)
        assert data == sim_data, \
            "check addr 0x%x row %d data %x != %x" % (addr, row, data, sim_data)

    for addr in range(memsize):
        data = yield from dcache_load(dut, addr*8, nc)
        assert data == sim_mem[addr], \
            "final check %x data %x != %x" % (addr*8, data, sim_mem[addr])


def dcache_regression_sim(dut, mem, nc=0):

    # start copy of mem
    sim_mem = deepcopy(mem)
    memsize = len(sim_mem)
    print ("mem len", memsize)

    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.priv_mode.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield

    addr = 0
    row = addr
    addr *= 8

    print ("random testing %d 0x%x row %d" % (i, addr, row))

    yield from dcache_load(dut, addr, nc)

    addr = 2
    sim_data = sim_mem[addr]
    row = addr
    addr *= 8

    print ("    load 0x%x row %d expect data 0x%x" % (addr, row, sim_data))
    data = yield from dcache_load(dut, addr, nc)
    assert data == sim_data, \
        "check addr 0x%x row %d data %x != %x" % (addr, row, data, sim_data)



def dcache_sim(dut, mem):
    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.priv_mode.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield

    # Cacheable read of address 4
    data = yield from dcache_load_m(dut, 0x58)
    print ("dcache m_load 0x58", hex(data))
    yield
    yield

    # Cacheable read of address 4
    data = yield from dcache_load_m(dut, 0x58)
    print ("dcache m_load 0x58", hex(data))
    yield
    yield

    return

    assert data == 0x0000001700000016, \
        f"data @%x=%x expected 0x0000001700000016" % (addr, data)

    # Cacheable read of address 20
    data = yield from dcache_load(dut, 0x20)
    addr = yield dut.d_in.addr
    assert data == 0x0000000900000008, \
        f"data @%x=%x expected 0x0000000900000008" % (addr, data)

    # Cacheable read of address 30
    data = yield from dcache_load(dut, 0x530)
    addr = yield dut.d_in.addr
    assert data == 0x0000014D0000014C, \
        f"data @%x=%x expected 0000014D0000014C" % (addr, data)

    # 2nd Cacheable read of address 30
    data = yield from dcache_load(dut, 0x530)
    addr = yield dut.d_in.addr
    assert data == 0x0000014D0000014C, \
        f"data @%x=%x expected 0000014D0000014C" % (addr, data)

    # Non-cacheable read of address 100
    data = yield from dcache_load(dut, 0x100, nc=1)
    addr = yield dut.d_in.addr
    assert data == 0x0000004100000040, \
        f"data @%x=%x expected 0000004100000040" % (addr, data)

    # Store at address 530
    yield from dcache_store(dut, 0x530, 0x121)

    # Store at address 30
    yield from dcache_store(dut, 0x530, 0x12345678)

    # 3nd Cacheable read of address 530
    data = yield from dcache_load(dut, 0x530)
    addr = yield dut.d_in.addr
    assert data == 0x12345678, \
        f"data @%x=%x expected 0x12345678" % (addr, data)

    # 4th Cacheable read of address 20
    data = yield from dcache_load(dut, 0x20)
    addr = yield dut.d_in.addr
    assert data == 0x0000000900000008, \
        f"data @%x=%x expected 0x0000000900000008" % (addr, data)

    yield
    yield
    yield
    yield


def tst_dcache(mem, test_fn, test_name):
    dut = DCache()

    memory = Memory(width=64, depth=len(mem), init=mem, simulate=True)
    sram = SRAM(memory=memory, granularity=8)

    m = Module()
    m.submodules.dcache = dut
    m.submodules.sram = sram

    m.d.comb += sram.bus.cyc.eq(dut.wb_out.cyc)
    m.d.comb += sram.bus.stb.eq(dut.wb_out.stb)
    m.d.comb += sram.bus.we.eq(dut.wb_out.we)
    m.d.comb += sram.bus.sel.eq(dut.wb_out.sel)
    m.d.comb += sram.bus.adr.eq(dut.wb_out.adr)
    m.d.comb += sram.bus.dat_w.eq(dut.wb_out.dat)

    m.d.comb += dut.wb_in.ack.eq(sram.bus.ack)
    m.d.comb += dut.wb_in.dat.eq(sram.bus.dat_r)

    dcache_write_gtkw(test_name)

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(test_fn(dut, mem)))
    with sim.write_vcd('test_dcache_m%s.vcd' % test_name):
        sim.run()


def dcache_write_gtkw(test_name):
    traces = [
        'clk',
        ('m_in', [
            'm_in_doall', 'm_in_addr[63:0]', 'm_in_pte[63:0]',
            'm_in_tlbie', 'm_in_tlbid', 'm_in_valid'
        ]),
        ('m_out', [
            'm_out_done', 'm_out_data[63:0]', 'm_out_err', 'm_out_stall'
        ]),
        ('d_in', [
            'd_in_load', 'd_in_nc', 'd_in_addr[63:0]', 'd_in_data[63:0]',
            'd_in_byte_sel[7:0]', 'd_in_valid'
        ]),
        ('d_out', [
            'd_out_valid', 'd_out_data[63:0]'
        ]),
        ('wb_out', [
            'wb_out_cyc', 'wb_out_stb', 'wb_out_we',
            'wb_out_adr[31:0]', 'wb_out_sel[7:0]', 'wb_out_dat[63:0]'
        ]),
        ('wb_in', [
            'wb_in_stall', 'wb_in_ack', 'wb_in_dat[63:0]'
        ])
    ]
    write_gtkw('test_dcache_m%s.gtkw' % test_name,
               'test_dcache_m%s.vcd' % test_name,
               traces, module='top.dcache')


if __name__ == '__main__':
    seed(0)
    dut = DCache()
    vl = rtlil.convert(dut, ports=[])
    with open("test_dcache.il", "w") as f:
        f.write(vl)

    if False:
        mem = []
        memsize = 16
        for i in range(memsize):
            mem.append(i)

        tst_dcache(mem, dcache_regression_sim, "simpleregression")

        mem = []
        memsize = 256
        for i in range(memsize):
            mem.append(i)

        tst_dcache(mem, dcache_random_sim, "random")

    mem = []
    for i in range(1024):
        mem.append((i*2)| ((i*2+1)<<32))

    tst_dcache(mem, dcache_sim, "")

