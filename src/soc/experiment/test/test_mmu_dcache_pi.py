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

from soc.config.test.test_pi2ls import pi_ld, pi_st, pi_ldst

from soc.experiment.mem_types import (LoadStore1ToMMUType,
                                 MMUToLoadStore1Type,
                                 MMUToDCacheType,
                                 DCacheToMMUType,
                                 MMUToICacheType)

from soc.experiment.mmu import MMU
from soc.experiment.dcache import DCache

#more imports 

from soc.experiment.l0_cache import L0CacheBuffer2
from nmigen import Module, Signal, Mux, Elaboratable, Cat, Const
from nmigen.cli import rtlil

from soc.config.test.test_pi2ls import pi_ld, pi_st, pi_ldst

from soc.experiment.pimem import PortInterfaceBase

from nmigen.compat.sim import run_simulation, Settle

# guess: those four need to be connected
#class DCacheToLoadStore1Type(RecordObject): dcache.d_out
#class LoadStore1ToDCacheType(RecordObject): dcache.d_in
#class LoadStore1ToMMUType(RecordObject):    mmu.l_in
#class MMUToLoadStore1Type(RecordObject):    mmu.l_out
# will take at least one week (10.10.2020)
# many unconnected signals

class TestMicrowattMemoryPortInterface(PortInterfaceBase):
    """TestMicrowattMemoryPortInterface

    This is a Test Class for MMU and DCache conforming to PortInterface
    """

    def __init__(self, mmu, dcache, regwid=64, addrwid=4,):
        super().__init__(regwid, addrwid)
        self.mmu = mmu
        self.dcache = dcache

    def set_wr_addr(self, m, addr, mask):
        m.d.comb += self.dcache.d_in.addr.eq(addr)
        m.d.comb += self.mmu.l_in.addr.eq(addr)
        m.d.comb += self.mmu.l_in.load.eq(0)
        m.d.comb += self.mmu.l_in.priv.eq(1)
        m.d.comb += self.mmu.l_in.valid.eq(1)

    def set_rd_addr(self, m, addr, mask):
        m.d.comb += self.dcache.d_in.addr.eq(addr)
        m.d.comb += self.mmu.l_in.addr.eq(addr)
        m.d.comb += self.mmu.l_in.load.eq(1)
        m.d.comb += self.mmu.l_in.priv.eq(1)
        m.d.comb += self.mmu.l_in.valid.eq(1)

    def set_wr_data(self, m, data, wen):
        m.d.comb += self.dcache.d_in.data.eq(data)  # write st to mem
        m.d.comb += self.dcache.d_in.load.eq(~wen)  # enable writes
        st_ok = Const(1, 1)
        return st_ok

        # LoadStore1ToDCacheType
        # valid
        # dcbz
        # nc
        # reserve
        # virt_mode
        # addr # TODO
        # byte_sel(8)

    def get_rd_data(self, m):
        # get data from dcache
        ld_ok = self.mmu.l_out.done
        data = self.dcache.d_out.data
        return data, ld_ok

        # DCacheToLoadStore1Type NC
        # store_done
        # error
        # cache_paradox

        return None

    def elaborate(self, platform):
        m = super().elaborate(platform)

        m.submodules.mmu = self.mmu
        m.submodules.dcache = self.dcache

        # link mmu and dcache together
        m.d.comb += self.dcache.m_in.eq(self.mmu.d_out)
        m.d.comb += self.mmu.d_in.eq(self.dcache.m_out)

        return m

    def ports(self):
        yield from super().ports()
        # TODO: memory ports

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
        yield dc.wb_in.dat.eq(data)
        print ("    DCACHE get %x data %x" % (addr, data))
        yield dc.wb_in.ack.eq(1)
        yield
        yield dc.wb_in.ack.eq(0)


def mmu_lookup(dut, addr):
    mmu = dut.mmu
    global stop

    print("pi_st")
    yield from pi_ld(dut.pi, addr, 1)
    print("pi_st_done")
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

    return phys_addr

def mmu_sim(dut):
    mmu = dut.mmu
    global stop
    yield mmu.rin.prtbl.eq(0x1000000) # set process table
    yield

    addr = 0x10000
    data = 0
    print("pi_st")

    # TODO mmu_lookup using port interface
    # set inputs 
    phys_addr = yield from mmu_lookup(dut, 0x10000)
    assert phys_addr == 0x40000

    phys_addr = yield from mmu_lookup(dut, 0x10000)
    assert phys_addr == 0x40000

    stop = True

def test_mmu():
    mmu = MMU()
    dcache = DCache()
    dut = TestMicrowattMemoryPortInterface(mmu, dcache)

    m = Module()
    m.submodules.dut = dut

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(mmu_sim(dut)))
    sim.add_sync_process(wrap(wb_get(dcache)))
    with sim.write_vcd('test_mmu_pi.vcd'):
        sim.run()

if __name__ == '__main__':
    test_mmu()
