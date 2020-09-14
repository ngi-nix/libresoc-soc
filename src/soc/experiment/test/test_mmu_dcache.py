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

stop = False


def wb_get(dc):
    """simulator process for getting memory load requests
    """

    global stop

    def b(x):
        return int.from_bytes(x.to_bytes(8, byteorder='little'),
                              byteorder='big', signed=False)

    mem = {0x10000:    # PARTITION_TABLE_2
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

    while not stop:
        while True: # wait for dc_valid
            if stop:
                return
            cyc = yield (dc.wb_out.cyc)
            stb = yield (dc.wb_out.stb)
            if cyc and stb:
                break
            yield
        addr = (yield dc.wb_out.adr) << 3
        if addr not in mem:
            print ("    DCACHE LOOKUP FAIL %x" % (addr))
            stop = True
            return

        yield
        data = mem[addr]
        yield dc.wb_in.data.eq(data)
        print ("dcache get %x data %x" % (addr, data))
        yield dc.wb_in.ack.eq(1)
        yield
        yield dc.wb_in.ack.eq(0)


def mmu_sim(mmu):
    global stop
    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    yield mmu.l_in.load.eq(1)
    yield mmu.l_in.priv.eq(1)
    yield mmu.l_in.addr.eq(0x10000)
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
    addr = yield mmu.d_out.addr
    pte = yield mmu.d_out.pte
    print ("translated done %d err %d badtree %d addr %x pte %x" % \
               (l_done, l_err, l_badtree, addr, pte))

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
    sim.add_sync_process(wrap(wb_get(dcache)))
    with sim.write_vcd('test_mmu.vcd'):
        sim.run()

if __name__ == '__main__':
    test_mmu()
