"""MMU PortInterface Test

quite basic, goes directly to the MMU to assert signals (does not
yet use PortInterface)
"""

from nmigen import (C, Module, Signal, Elaboratable, Mux, Cat, Repl, Signal)
from nmigen.cli import main
from nmigen.cli import rtlil
from nmutil.mask import Mask, masked
from nmutil.util import Display
from random import randint, seed

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

#def dumpmem(mem,fn):
#    f = open(fn,"w")
#    for cell in mem:
#        f.write(str(hex(cell))+"="+str(hex(mem[cell]))+"\n")

def wb_get(wb, mem):
    """simulator process for getting memory load requests
    """

    global stop
    assert(stop==False)

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

    global stop
    stop = False

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


def ldst_sim_radixmiss(dut):
    mmu = dut.submodules.mmu
    global stop
    stop = False

    yield mmu.rin.prtbl.eq(1<<40) # set process table
    yield

    data = yield from pi_ld(dut.submodules.ldst.pi, 0x10000000, 8, msr_pr=1)
    print ("radixmiss ld data", hex(data))

    yield
    stop = True

def ldst_sim_dcache_regression(dut):
    mmu = dut.submodules.mmu
    global stop
    stop = False

    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    addr = 0x10000
    data = yield from pi_ld(dut.submodules.ldst.pi, addr, 8, msr_pr=1)
    print ("=== dcache_regression ld data", hex(data))
    assert(data == 0xdeadbeef01234567)

    yield
    stop = True

def ldst_sim_dcache_random(dut):
    mmu = dut.submodules.mmu
    pi = dut.submodules.ldst.pi
    global stop
    stop = False

    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    memsize = 64

    for i in range(16):
        addr = randint(0, memsize-1)
        data = randint(0, (1<<64)-1)
        addr *= 8
        addr += 0x10000

        yield from pi_st(pi, addr, data, 8, msr_pr=1)
        yield

        ld_data = yield from pi_ld(pi, addr, 8, msr_pr=1)

        eq = (data==ld_data)
        print ("dcache_random values", hex(addr), hex(data), hex(ld_data), eq)
        assert(data==ld_data)   ## investigate why this fails -- really seldom

    yield
    stop = True

def ldst_sim_dcache_first(dut): # this test is likely to fail
    mmu = dut.submodules.mmu
    pi = dut.submodules.ldst.pi
    global stop
    stop = False

    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    # failed ramdom data
    addr = 65888
    data = 0x8c5a3e460d71f0b4

    # known to fail without bugfix in src/soc/fu/ldst/loadstore.py
    yield from pi_st(pi, addr, data, 8, msr_pr=1)
    yield

    ld_data = yield from pi_ld(pi, addr, 8, msr_pr=1)

    print ("addr",addr)
    print ("dcache_first ld data", hex(data), hex(ld_data))

    assert(data==ld_data)

    yield
    stop = True

def test_radixmiss_mmu():

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

    sim.add_sync_process(wrap(ldst_sim_radixmiss(m)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi_radix_miss.vcd'):
        sim.run()

def test_dcache_regression():

    m, cmpi = setup_mmu()

    # dcache_load at addr 0
    mem = {
           0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           b(0x800000000100000b),

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           b(0x8000000000040009),

           0x40000:     # RADIX_SECOND_LEVEL
                        # V = 1 L = 1 SW = 0 RPN = 0
                        # R = 1 C = 1 ATT = 0 EAA 0x7
           b(0xc000000000000183),

           0x1000000:   # PROCESS_TABLE_3
                        # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           b(0x40000000000300ad),

           # data to return
           0x10000: 0xdeadbeef01234567,
           0x10008: 0xfeedf00ff001a5a5
    }

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(ldst_sim_dcache_regression(m)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi_radix_miss.vcd'):
        sim.run()

def test_dcache_random():

    m, cmpi = setup_mmu()

    # dcache_load at addr 0
    mem = {
           0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           b(0x800000000100000b),

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           b(0x8000000000040009),

           0x40000:     # RADIX_SECOND_LEVEL
                        # V = 1 L = 1 SW = 0 RPN = 0
                        # R = 1 C = 1 ATT = 0 EAA 0x7
           b(0xc000000000000183),

           0x1000000:   # PROCESS_TABLE_3
                        # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           b(0x40000000000300ad),
    }

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(ldst_sim_dcache_random(m)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi_random.vcd'):
        sim.run()

def ldst_sim_dcache_random2(dut, mem):
    mmu = dut.submodules.mmu
    pi = dut.submodules.ldst.pi
    global stop
    stop = False

    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    memsize = 64

    refs = [
         ## random values from a failed test
         #[0x100e0,0xf553b658ba7e1f51,0,0], ## 1
         #[0x10150,0x12c95a730df1cee7,0,0], ## 2
         #[0x10080,0x5a921ae06674cd81,0,0], ## 3
         #[0x100f8,0x4fea5eab80090fa5,0,0], ## 4
         #[0x10080,0xd481432d17a340be,0,0], ## 5
         #[0x10060,0x8553fcf29526fb32,0,0], ## 6
         [0x101d0,0x327c967c8be30ded,0,0], ## 7
         [0x101e0,0x8f15d8d05d25b151,1,0]  ## 8
         #uncommenting line 7 will cause the original test not to fail

    ]

    c = 0
    for i in refs:
        addr = i[0]
        data = i[1]
        c1 = i[2]
        c2 = i[3]

        print("== write: wb_get")

        for i in range(0,c1):
            print("before_pi_st")
            yield

        yield from pi_st(pi, addr, data, 8, msr_pr=1)
        yield

        for i in range(0,c2):
            print("before_pi_ld")
            yield

        print("== read: wb_get")
        ld_data = yield from pi_ld(pi, addr, 8, msr_pr=1)

        #dumpmem(mem,"/tmp/dumpmem"+str(c)+".txt")
        #c += 1

        eq = (data==ld_data)
        print ("dcache_random values", hex(addr), hex(data), hex(ld_data), eq)
        assert(data==ld_data)   ## investigate why this fails -- really seldom

    yield
    stop = True

def test_dcache_random2():

    m, cmpi = setup_mmu()

    # dcache_load at addr 0
    mem = {
           0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           b(0x800000000100000b),

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           b(0x8000000000040009),

           0x40000:     # RADIX_SECOND_LEVEL
                        # V = 1 L = 1 SW = 0 RPN = 0
                        # R = 1 C = 1 ATT = 0 EAA 0x7
           b(0xc000000000000183),

           0x1000000:   # PROCESS_TABLE_3
                        # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           b(0x40000000000300ad),

           ###0x101e0:0x8f15d8d05d25b152      ## flush cache -- then check again
    }

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(ldst_sim_dcache_random2(m, mem)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi_random2.vcd'):
        sim.run()

def test_dcache_first():

    m, cmpi = setup_mmu()

    # dcache_load at addr 0
    mem = {
           0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           b(0x800000000100000b),

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           b(0x8000000000040009),

           0x40000:     # RADIX_SECOND_LEVEL
                        # V = 1 L = 1 SW = 0 RPN = 0
                        # R = 1 C = 1 ATT = 0 EAA 0x7
           b(0xc000000000000183),

           0x1000000:   # PROCESS_TABLE_3
                        # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           b(0x40000000000300ad),
    }

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(ldst_sim_dcache_first(m)))
    sim.add_sync_process(wrap(wb_get(cmpi.wb_bus(), mem)))
    with sim.write_vcd('test_ldst_pi_first.vcd'):
        sim.run()

if __name__ == '__main__':
    test_mmu()
    test_misalign_mmu()
    test_radixmiss_mmu()
    ### tests taken from src/soc/experiment/test/test_dcache.py
    test_dcache_regression()
    test_dcache_first()
    test_dcache_random() #sometimes fails
    test_dcache_random2() #reproduce error
