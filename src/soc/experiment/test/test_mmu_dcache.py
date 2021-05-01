from nmigen import (C, Module, Signal, Elaboratable, Mux, Cat, Repl, Signal)
from nmigen.cli import main
from nmigen.cli import rtlil
from nmutil.iocontrol import RecordObject
from nmutil.byterev import byte_reverse
from nmutil.mask import Mask, masked
from nmutil.util import Display

if True:
    from nmigen.back.pysim import Simulator, Delay, Settle
else:
    from nmigen.sim.cxxsim import Simulator, Delay, Settle
from nmutil.util import wrap

from soc.experiment.mem_types import (LoadStore1ToMMUType,
                                 MMUToLoadStore1Type,
                                 MMUToDCacheType,
                                 DCacheToMMUType,
                                 MMUToICacheType)

from soc.experiment.mmu import MMU
from soc.experiment.dcache import DCache
from soc.experiment.icache import ICache

import random

stop = False

def set_stop(newval):
    global stop
    stop = newval


def b(x):
    return int.from_bytes(x.to_bytes(8, byteorder='little'),
                          byteorder='big', signed=False)


default_mem = { 0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
                b(0x800000000100000b),

                0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
                b(0x8000000000040009),

                0x40000:     # RADIX_SECOND_LEVEL
                        # 	   V = 1 L = 1 SW = 0 RPN = 0
	                    # R = 1 C = 1 ATT = 0 EAA 0x7
                b(0xc000000000000187),

                0x1000000:   # PROCESS_TABLE_3
                       # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
                b(0x40000000000300ad),
            }


def wb_get(c, mem, name):
    """simulator process for getting memory load requests
    """

    logfile = open("/tmp/wb_get.log","w")

    def log(msg):
        logfile.write(msg+"\n")
        print(msg)

    global stop
    while not stop:
        while True: # wait for dc_valid
            if stop:
                log("stop")
                return
            cyc = yield (c.wb_out.cyc)
            stb = yield (c.wb_out.stb)
            if cyc and stb:
                break
            yield
        addr = (yield c.wb_out.adr) << 3
        if addr not in mem:
            log("%s LOOKUP FAIL %x" % (name, addr))
            stop = True
            return

        yield
        data = mem[addr]
        yield c.wb_in.dat.eq(data)
        log("%s get %x data %x" % (name, addr, data))
        yield c.wb_in.ack.eq(1)
        yield
        yield c.wb_in.ack.eq(0)


def icache_sim(dut, mem):
    i_out = dut.i_in
    i_in  = dut.i_out
    m_out = dut.m_in

    for k,v in mem.items():
        yield i_in.valid.eq(0)
        yield i_out.priv_mode.eq(1)
        yield i_out.req.eq(0)
        yield i_out.nia.eq(0)
        yield i_out.stop_mark.eq(0)
        yield m_out.tlbld.eq(0)
        yield m_out.tlbie.eq(0)
        yield m_out.addr.eq(0)
        yield m_out.pte.eq(0)
        yield
        yield
        yield
        yield
        yield i_out.req.eq(1)
        yield i_out.nia.eq(C(k, 64))
        while True:
            yield
            valid = yield i_in.valid
            if valid:
                break
        nia   = yield i_out.nia
        insn  = yield i_in.insn
        yield
        assert insn == v, \
            "insn @%x=%x expected %x" % (nia, insn, v)
        yield i_out.req.eq(0)
        yield


def test_icache_il():
    dut = ICache()
    vl = rtlil.convert(dut, ports=[])
    with open("test_icache.il", "w") as f:
        f.write(vl)


def test_icache():
    # create a random set of addresses and "instructions" at those addresses
    mem = {}
    # fail 'AssertionError: insn @1d8=0 expected 61928a6100000000'
    #random.seed(41)
    # fail infinite loop 'cache read adr: 24 data: 0'
    random.seed(43)
    for i in range(3):
        mem[random.randint(0, 1<<10)] = b(random.randint(0,1<<32))

    # set up module for simulation
    m = Module()
    icache = ICache()
    m.submodules.icache = icache

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    # read from "memory" process and corresponding wishbone "read" process
    sim.add_sync_process(wrap(icache_sim(icache, mem)))
    sim.add_sync_process(wrap(wb_get(icache, mem, "ICACHE")))
    with sim.write_vcd('test_icache.vcd'):
        sim.run()


def mmu_lookup(mmu, addr):
    global stop

    yield mmu.l_in.load.eq(1)
    yield mmu.l_in.priv.eq(1)
    yield mmu.l_in.addr.eq(addr)
    yield mmu.l_in.valid.eq(1)
    while not stop: # wait for dc_valid / err
        l_done = yield (mmu.l_out.done)
        l_err = yield (mmu.l_out.err)
        l_badtree = yield (mmu.l_out.badtree)
        l_permerr = yield (mmu.l_out.perm_error)
        l_rc_err = yield (mmu.l_out.rc_error)
        l_segerr = yield (mmu.l_out.segerr)
        l_invalid = yield (mmu.l_out.invalid)
        if (l_done or l_err or l_badtree or
            l_permerr or l_rc_err or l_segerr or l_invalid):
            break
        yield
    phys_addr = yield mmu.d_out.addr
    pte = yield mmu.d_out.pte
    print ("translated done %d err %d badtree %d addr %x pte %x" % \
               (l_done, l_err, l_badtree, phys_addr, pte))
    yield
    yield mmu.l_in.valid.eq(0)

    return phys_addr


def mmu_sim(mmu):
    global stop
    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    phys_addr = yield from mmu_lookup(mmu, 0x10000)
    assert phys_addr == 0x40000

    phys_addr = yield from mmu_lookup(mmu, 0x10000)
    assert phys_addr == 0x40000

    stop = True


def test_mmu():
    mmu = MMU()
    dcache = DCache()
    m = Module()
    m.submodules.mmu = mmu
    m.submodules.dcache = dcache

    # link mmu and dcache together
    m.d.comb += dcache.m_in.eq(mmu.d_out)
    m.d.comb += mmu.d_in.eq(dcache.m_out)

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(mmu_sim(mmu)))
    sim.add_sync_process(wrap(wb_get(dcache, default_mem, "DCACHE")))
    with sim.write_vcd('test_mmu.vcd'):
        sim.run()


if __name__ == '__main__':
    test_mmu()
    #test_icache_il()
    #test_icache()
