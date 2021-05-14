"""MMU PortInterface Test

quite basic, goes directly to the MMU to assert signals (does not
yet use PortInterface)
"""

from nmigen import (C, Module, Signal, Elaboratable, Mux, Cat, Repl, Signal)
from nmigen.cli import main
from nmigen.cli import rtlil
from nmutil.mask import Mask, masked
from nmutil.util import Display

if True:
    from nmigen.back.pysim import Simulator, Delay, Settle
else:
    from nmigen.sim.cxxsim import Simulator, Delay, Settle
from nmutil.util import wrap

from soc.config.test.test_pi2ls import pi_ld, pi_st, pi_ldst
from soc.config.test.test_loadstore import TestMemPspec
from soc.config.loadstore import ConfigMemoryPortInterface

from soc.fu.ldst.loadstore import LoadStore1
from soc.experiment.mmu import MMU

from nmigen.compat.sim import run_simulation


stop = False

def b(x): # byte-reverse function
    return int.from_bytes(x.to_bytes(8, byteorder='little'),
                          byteorder='big', signed=False)

def wb_get(wb, mem):
    """simulator process for getting memory load requests
    """

    global stop

    while not stop:
        while True: # wait for dc_valid
            if stop:
                return
            cyc = yield (wb.cyc)
            stb = yield (wb.stb)
            if cyc and stb:
                break
            yield
        addr = (yield wb.adr) << 3
        if addr not in mem:
            print ("    WB LOOKUP NO entry @ %x, returning zero" % (addr))

        # read or write?
        we = (yield wb.we)
        if we:
            store = (yield wb.dat_w)
            sel = (yield wb.sel)
            data = mem.get(addr, 0)
            # note we assume 8-bit sel, here
            res = 0
            for i in range(8):
                mask = 0xff << (i*8)
                if sel & (1<<i):
                    res |= store & mask
                else:
                    res |= data & mask
            mem[addr] = res
            print ("    DCACHE set %x mask %x data %x" % (addr, sel, res))
        else:
            data = mem.get(addr, 0)
            yield wb.dat_r.eq(data)
            print ("    DCACHE get %x data %x" % (addr, data))

        yield wb.ack.eq(1)
        yield
        yield wb.ack.eq(0)
        yield


def mmu_lookup(dut, addr):
    mmu = dut.submodules.mmu
    global stop

    print("pi_ld", hex(addr))
    data = yield from pi_ld(dut.submodules.ldst.pi, addr, 4, msr_pr=1)
    print("pi_ld done, data", hex(data))
    """
    # original test code kept for reference
    while not stop: # wait for dc_valid / err
        print("waiting for mmu")
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
    """
    phys_addr = yield mmu.d_out.addr
    pte = yield mmu.d_out.pte
    l_done = yield (mmu.l_out.done)
    l_err = yield (mmu.l_out.err)
    l_badtree = yield (mmu.l_out.badtree)
    print ("translated done %d err %d badtree %d addr %x pte %x" % \
               (l_done, l_err, l_badtree, phys_addr, pte))
    yield
    yield mmu.l_in.valid.eq(0)

    return data


def ldst_sim(dut):
    mmu = dut.submodules.mmu
    global stop
    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    # expecting this data to return
    # 0x1000: 0xdeadbeef01234567,
    # 0x1008: 0xfeedf00ff001a5a5

    addr = 0x1000
    print("pi_ld")

    # TODO mmu_lookup using port interface
    # set inputs
    data = yield from mmu_lookup(dut, addr)
    assert data == 0x1234567

    data = yield from mmu_lookup(dut, addr+8)
    assert data == 0xf001a5a5
    #assert phys_addr == addr # happens to be the same (for this example)

    data = yield from mmu_lookup(dut, addr+4)
    assert data == 0xdeadbeef

    data = yield from mmu_lookup(dut, addr+8)
    assert data == 0xf001a5a5

    yield from pi_st(dut.submodules.ldst.pi, addr+4, 0x10015a5a, 4, msr_pr=1)

    data = yield from mmu_lookup(dut, addr+4)
    assert data == 0x10015a5a

    yield
    yield

    stop = True

def setup_mmu():

    pspec = TestMemPspec(ldst_ifacetype='mmu_cache_wb',
                         imem_ifacetype='',
                         addr_wid=48,
                         #disable_cache=True, # hmmm...
                         mask_wid=8,
                         reg_wid=64)

    m = Module()
    comb = m.d.comb
    cmpi = ConfigMemoryPortInterface(pspec)
    m.submodules.ldst = ldst = cmpi.pi
    m.submodules.mmu = mmu = MMU()
    dcache = ldst.dcache

    l_in, l_out = mmu.l_in, mmu.l_out
    d_in, d_out = dcache.d_in, dcache.d_out
    wb_out, wb_in = dcache.wb_out, dcache.wb_in

    # link mmu and dcache together
    m.d.comb += dcache.m_in.eq(mmu.d_out) # MMUToDCacheType
    m.d.comb += mmu.d_in.eq(dcache.m_out) # DCacheToMMUType

    # link ldst and MMU together
    comb += l_in.eq(ldst.m_out)
    comb += ldst.m_in.eq(l_out)

    return m, cmpi


def test_mmu():

    m, cmpi = setup_mmu()

    # virtual "memory" to use for this test

    mem = {0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           b(0x800000000100000b),

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           b(0x8000000000040009),

           0x40000:     # RADIX_SECOND_LEVEL
                        # 	   V = 1 L = 1 SW = 0 RPN = 0
                           # R = 1 C = 1 ATT = 0 EAA 0x7
           b(0xc000000000000183),

          0x1000000:   # PROCESS_TABLE_3
                       # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           b(0x40000000000300ad),

         # data to return
          0x1000: 0xdeadbeef01234567,
          0x1008: 0xfeedf00ff001a5a5
          }


    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(ldst_sim(m)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi.vcd'):
        sim.run()

def ldst_sim_misalign(dut):
    mmu = dut.submodules.mmu
    global stop
    stop = False

    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    data = yield from pi_ld(dut.submodules.ldst.pi, 0x1007, 8, msr_pr=1)
    print ("misalign ld data", hex(data))

    yield
    stop = True


def test_misalign_mmu():

    m, cmpi = setup_mmu()

    # virtual "memory" to use for this test

    mem = {0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           b(0x800000000100000b),

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           b(0x8000000000040009),

           0x40000:     # RADIX_SECOND_LEVEL
                        # 	   V = 1 L = 1 SW = 0 RPN = 0
                           # R = 1 C = 1 ATT = 0 EAA 0x7
           b(0xc000000000000183),

          0x1000000:   # PROCESS_TABLE_3
                       # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           b(0x40000000000300ad),

         # data to return
          0x1000: 0xdeadbeef01234567,
          0x1008: 0xfeedf00ff001a5a5
          }


    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(ldst_sim_misalign(m)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi_misalign.vcd'):
        sim.run()


if __name__ == '__main__':
    test_mmu()
    test_misalign_mmu()
