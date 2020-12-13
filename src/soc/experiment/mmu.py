# MMU
#
# License for original copyright mmu.vhdl by microwatt authors: CC4
# License for copyrighted modifications made in mmu.py: LGPLv3+
#
# This derivative work although includes CC4 licensed material is
# covered by the LGPLv3+

"""MMU

based on Anton Blanchard microwatt mmu.vhdl

"""
from enum import Enum, unique
from nmigen import (C, Module, Signal, Elaboratable, Mux, Cat, Repl, Signal)
from nmigen.cli import main
from nmigen.cli import rtlil
from nmutil.iocontrol import RecordObject
from nmutil.byterev import byte_reverse
from nmutil.mask import Mask, masked
from nmutil.util import Display

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmutil.util import wrap

from soc.experiment.mem_types import (LoadStore1ToMMUType,
                                 MMUToLoadStore1Type,
                                 MMUToDCacheType,
                                 DCacheToMMUType,
                                 MMUToICacheType)


@unique
class State(Enum):
    IDLE = 0            # zero is default on reset for r.state
    DO_TLBIE = 1
    TLB_WAIT = 2
    PROC_TBL_READ = 3
    PROC_TBL_WAIT = 4
    SEGMENT_CHECK = 5
    RADIX_LOOKUP = 6
    RADIX_READ_WAIT = 7
    RADIX_LOAD_TLB = 8
    RADIX_FINISH = 9


class RegStage(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        # latched request from loadstore1
        self.valid = Signal()
        self.iside = Signal()
        self.store = Signal()
        self.priv = Signal()
        self.addr = Signal(64)
        self.inval_all = Signal()
        # config SPRs
        self.prtbl = Signal(64)
        self.pid = Signal(32)
        # internal state
        self.state = Signal(State) # resets to IDLE
        self.done = Signal()
        self.err = Signal()
        self.pgtbl0 = Signal(64)
        self.pt0_valid = Signal()
        self.pgtbl3 = Signal(64)
        self.pt3_valid = Signal()
        self.shift = Signal(6)
        self.mask_size = Signal(5)
        self.pgbase = Signal(56)
        self.pde = Signal(64)
        self.invalid = Signal()
        self.badtree = Signal()
        self.segerror = Signal()
        self.perm_err = Signal()
        self.rc_error = Signal()


class MMU(Elaboratable):
    """Radix MMU

    Supports 4-level trees as in arch 3.0B, but not the
    two-step translation for guests under a hypervisor
    (i.e. there is no gRA -> hRA translation).
    """
    def __init__(self):
        self.l_in  = LoadStore1ToMMUType()
        self.l_out = MMUToLoadStore1Type()
        self.d_out = MMUToDCacheType()
        self.d_in  = DCacheToMMUType()
        self.i_out = MMUToICacheType()

    def radix_tree_idle(self, m, l_in, r, v):
        comb = m.d.comb
        sync = m.d.sync

        pt_valid = Signal()
        pgtbl = Signal(64)
        rts = Signal(6)
        mbits = Signal(6)

        with m.If(~l_in.addr[63]):
            comb += pgtbl.eq(r.pgtbl0)
            comb += pt_valid.eq(r.pt0_valid)
        with m.Else():
            comb += pgtbl.eq(r.pgtbl3)
            comb += pt_valid.eq(r.pt3_valid)

        # rts == radix tree size, number of address bits
        # being translated
        comb += rts.eq(Cat(pgtbl[5:8], pgtbl[61:63]))

        # mbits == number of address bits to index top
        # level of tree
        comb += mbits.eq(pgtbl[0:5])

        # set v.shift to rts so that we can use finalmask
        # for the segment check
        comb += v.shift.eq(rts)
        comb += v.mask_size.eq(mbits[0:5])
        comb += v.pgbase.eq(Cat(C(0, 8), pgtbl[8:56]))

        with m.If(l_in.valid):
            comb += v.addr.eq(l_in.addr)
            comb += v.iside.eq(l_in.iside)
            comb += v.store.eq(~(l_in.load | l_in.iside))
            comb += v.priv.eq(l_in.priv)

            comb += Display("state %d l_in.valid addr %x iside %d store %d "
                            "rts %x mbits %x pt_valid %d",
                            v.state, v.addr, v.iside, v.store,
                            rts, mbits, pt_valid)

            with m.If(l_in.tlbie):
                # Invalidate all iTLB/dTLB entries for
                # tlbie with RB[IS] != 0 or RB[AP] != 0,
                # or for slbia
                comb += v.inval_all.eq(l_in.slbia
                                       | l_in.addr[11]
                                       | l_in.addr[10]
                                       | l_in.addr[7]
                                       | l_in.addr[6]
                                       | l_in.addr[5]
                                      )
                # The RIC field of the tlbie instruction
                # comes across on the sprn bus as bits 2--3.
                # RIC=2 flushes process table caches.
                with m.If(l_in.sprn[3]):
                    comb += v.pt0_valid.eq(0)
                    comb += v.pt3_valid.eq(0)
                comb += v.state.eq(State.DO_TLBIE)
            with m.Else():
                comb += v.valid.eq(1)
                with m.If(~pt_valid):
                    # need to fetch process table entry
                    # set v.shift so we can use finalmask
                    # for generating the process table
                    # entry address
                    comb += v.shift.eq(r.prtbl[0:5])
                    comb += v.state.eq(State.PROC_TBL_READ)

                with m.Elif(mbits == 0):
                    # Use RPDS = 0 to disable radix tree walks
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.invalid.eq(1)
                with m.Else():
                    comb += v.state.eq(State.SEGMENT_CHECK)

        with m.If(l_in.mtspr):
            # Move to PID needs to invalidate L1 TLBs
            # and cached pgtbl0 value.  Move to PRTBL
            # does that plus invalidating the cached
            # pgtbl3 value as well.
            with m.If(~l_in.sprn[9]):
                comb += v.pid.eq(l_in.rs[0:32])
            with m.Else():
                comb += v.prtbl.eq(l_in.rs)
                comb += v.pt3_valid.eq(0)

            comb += v.pt0_valid.eq(0)
            comb += v.inval_all.eq(1)
            comb += v.state.eq(State.DO_TLBIE)

    def proc_tbl_wait(self, m, v, r, data):
        comb = m.d.comb
        with m.If(r.addr[63]):
            comb += v.pgtbl3.eq(data)
            comb += v.pt3_valid.eq(1)
        with m.Else():
            comb += v.pgtbl0.eq(data)
            comb += v.pt0_valid.eq(1)

        rts = Signal(6)
        mbits = Signal(6)

        # rts == radix tree size, # address bits being translated
        comb += rts.eq(Cat(data[5:8], data[61:63]))

        # mbits == # address bits to index top level of tree
        comb += mbits.eq(data[0:5])

        # set v.shift to rts so that we can use finalmask for the segment check
        comb += v.shift.eq(rts)
        comb += v.mask_size.eq(mbits[0:5])
        comb += v.pgbase.eq(Cat(C(0, 8), data[8:56]))

        with m.If(mbits):
            comb += v.state.eq(State.SEGMENT_CHECK)
        with m.Else():
            comb += v.state.eq(State.RADIX_FINISH)
            comb += v.invalid.eq(1)

    def radix_read_wait(self, m, v, r, d_in, data):
        comb = m.d.comb
        sync = m.d.sync

        perm_ok = Signal()
        rc_ok = Signal()
        mbits = Signal(6)
        valid = Signal()
        leaf = Signal()
        badtree = Signal()

        comb += Display("RDW %016x done %d "
                        "perm %d rc %d mbits %d shf %d "
                        "valid %d leaf %d bad %d",
                        data, d_in.done, perm_ok, rc_ok,
                        mbits, r.shift, valid, leaf, badtree)

        # set pde
        comb += v.pde.eq(data)

        # test valid bit
        comb += valid.eq(data[63]) # valid=data[63]
        comb += leaf.eq(data[62]) # valid=data[63]

        comb += v.pde.eq(data)
        # valid & leaf
        with m.If(valid):
            with m.If(leaf):
                # check permissions and RC bits
                with m.If(r.priv | ~data[3]):
                    with m.If(~r.iside):
                        comb += perm_ok.eq(data[1] | (data[2] & ~r.store))
                    with m.Else():
                        # no IAMR, so no KUEP support for now
                        # deny execute permission if cache inhibited
                        comb += perm_ok.eq(data[0] & ~data[5])

                comb += rc_ok.eq(data[8] & (data[7] | ~r.store))
                with m.If(perm_ok & rc_ok):
                    comb += v.state.eq(State.RADIX_LOAD_TLB)
                with m.Else():
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.perm_err.eq(~perm_ok)
                    # permission error takes precedence over RC error
                    comb += v.rc_error.eq(perm_ok)

            # valid & !leaf
            with m.Else():
                comb += mbits.eq(data[0:5])
                comb += badtree.eq((mbits < 5) |
                                   (mbits > 16) |
                                   (mbits > r.shift))
                with m.If(badtree):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)
                with m.Else():
                    comb += v.shift.eq(r.shift - mbits)
                    comb += v.mask_size.eq(mbits[0:5])
                    comb += v.pgbase.eq(Cat(C(0, 8), data[8:56]))
                    comb += v.state.eq(State.RADIX_LOOKUP)

        with m.Else():
            # non-present PTE, generate a DSI
            comb += v.state.eq(State.RADIX_FINISH)
            comb += v.invalid.eq(1)

    def segment_check(self, m, v, r, data, finalmask):
        comb = m.d.comb

        mbits = Signal(6)
        nonzero = Signal()
        comb += mbits.eq(r.mask_size)
        comb += v.shift.eq(r.shift + (31 - 12) - mbits)
        comb += nonzero.eq((r.addr[31:62] & ~finalmask[0:31]).bool())
        with m.If((r.addr[63] ^ r.addr[62]) | nonzero):
            comb += v.state.eq(State.RADIX_FINISH)
            comb += v.segerror.eq(1)
        with m.Elif((mbits < 5) | (mbits > 16) |
                    (mbits > (r.shift + (31-12)))):
            comb += v.state.eq(State.RADIX_FINISH)
            comb += v.badtree.eq(1)
        with m.Else():
            comb += v.state.eq(State.RADIX_LOOKUP)

    def mmu_0(self, m, r, rin, l_in, l_out, d_out, addrsh, mask):
        comb = m.d.comb
        sync = m.d.sync

        # Multiplex internal SPR values back to loadstore1,
        # selected by l_in.sprn.
        with m.If(l_in.sprn[9]):
            comb += l_out.sprval.eq(r.prtbl)
        with m.Else():
            comb += l_out.sprval.eq(r.pid)

        with m.If(rin.valid):
            sync += Display("MMU got tlb miss for %x", rin.addr)

        with m.If(l_out.done):
            sync += Display("MMU completing op without error")

        with m.If(l_out.err):
            sync += Display("MMU completing op with err invalid"
                            "%d badtree=%d", l_out.invalid, l_out.badtree)

        with m.If(rin.state == State.RADIX_LOOKUP):
            sync += Display ("radix lookup shift=%d msize=%d",
                            rin.shift, rin.mask_size)

        with m.If(r.state == State.RADIX_LOOKUP):
            sync += Display(f"send load addr=%x addrsh=%d mask=%x",
                            d_out.addr, addrsh, mask)
        sync += r.eq(rin)

    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        addrsh = Signal(16)
        mask = Signal(16)
        finalmask = Signal(44)

        self.rin = rin = RegStage("r_in")
        r = RegStage("r")

        l_in  = self.l_in
        l_out = self.l_out
        d_out = self.d_out
        d_in  = self.d_in
        i_out = self.i_out

        self.mmu_0(m, r, rin, l_in, l_out, d_out, addrsh, mask)

        v = RegStage()
        dcreq = Signal()
        tlb_load = Signal()
        itlb_load = Signal()
        tlbie_req = Signal()
        prtbl_rd = Signal()
        effpid = Signal(32)
        prtb_adr = Signal(64)
        pgtb_adr = Signal(64)
        pte = Signal(64)
        tlb_data = Signal(64)
        addr = Signal(64)

        comb += v.eq(r)
        comb += v.valid.eq(0)
        comb += dcreq.eq(0)
        comb += v.done.eq(0)
        comb += v.err.eq(0)
        comb += v.invalid.eq(0)
        comb += v.badtree.eq(0)
        comb += v.segerror.eq(0)
        comb += v.perm_err.eq(0)
        comb += v.rc_error.eq(0)
        comb += tlb_load.eq(0)
        comb += itlb_load.eq(0)
        comb += tlbie_req.eq(0)
        comb += v.inval_all.eq(0)
        comb += prtbl_rd.eq(0)

        # Radix tree data structures in memory are
        # big-endian, so we need to byte-swap them
        data = byte_reverse(m, "data", d_in.data, 8)

        # generate mask for extracting address fields for PTE addr generation
        m.submodules.pte_mask = pte_mask = Mask(16-5)
        comb += pte_mask.shift.eq(r.mask_size - 5)
        comb += mask.eq(Cat(C(0x1f, 5), pte_mask.mask))

        # generate mask for extracting address bits to go in
        # TLB entry in order to support pages > 4kB
        m.submodules.tlb_mask = tlb_mask = Mask(44)
        comb += tlb_mask.shift.eq(r.shift)
        comb += finalmask.eq(tlb_mask.mask)

        with m.If(r.state != State.IDLE):
            sync += Display("MMU state %d %016x", r.state, data)

        with m.Switch(r.state):
            with m.Case(State.IDLE):
                self.radix_tree_idle(m, l_in, r, v)

            with m.Case(State.DO_TLBIE):
                comb += dcreq.eq(1)
                comb += tlbie_req.eq(1)
                comb += v.state.eq(State.TLB_WAIT)

            with m.Case(State.TLB_WAIT):
                with m.If(d_in.done):
                    comb += v.state.eq(State.RADIX_FINISH)

            with m.Case(State.PROC_TBL_READ):
                sync += Display("   TBL_READ %016x", prtb_adr)
                comb += dcreq.eq(1)
                comb += prtbl_rd.eq(1)
                comb += v.state.eq(State.PROC_TBL_WAIT)

            with m.Case(State.PROC_TBL_WAIT):
                with m.If(d_in.done):
                    self.proc_tbl_wait(m, v, r, data)

                with m.If(d_in.err):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)

            with m.Case(State.SEGMENT_CHECK):
                self.segment_check(m, v, r, data, finalmask)

            with m.Case(State.RADIX_LOOKUP):
                sync += Display("   RADIX_LOOKUP")
                comb += dcreq.eq(1)
                comb += v.state.eq(State.RADIX_READ_WAIT)

            with m.Case(State.RADIX_READ_WAIT):
                sync += Display("   READ_WAIT")
                with m.If(d_in.done):
                    self.radix_read_wait(m, v, r, d_in, data)
                with m.If(d_in.err):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)

            with m.Case(State.RADIX_LOAD_TLB):
                comb +=  tlb_load.eq(1)
                with m.If(~r.iside):
                    comb += dcreq.eq(1)
                    comb += v.state.eq(State.TLB_WAIT)
                with m.Else():
                    comb += itlb_load.eq(1)
                    comb += v.state.eq(State.IDLE)

            with m.Case(State.RADIX_FINISH):
                sync += Display("   RADIX_FINISH")
                comb += v.state.eq(State.IDLE)

        with m.If((v.state == State.RADIX_FINISH) |
                 ((v.state == State.RADIX_LOAD_TLB) & r.iside)):
            comb += v.err.eq(v.invalid | v.badtree | v.segerror
                             | v.perm_err | v.rc_error)
            comb += v.done.eq(~v.err)

        with m.If(~r.addr[63]):
            comb += effpid.eq(r.pid)

        pr24 = Signal(24, reset_less=True)
        comb += pr24.eq(masked(r.prtbl[12:36], effpid[8:32], finalmask))
        comb += prtb_adr.eq(Cat(C(0, 4), effpid[0:8], pr24, r.prtbl[36:56]))

        pg16 = Signal(16, reset_less=True)
        comb += pg16.eq(masked(r.pgbase[3:19], addrsh, mask))
        comb += pgtb_adr.eq(Cat(C(0, 3), pg16, r.pgbase[19:56]))

        pd44 = Signal(44, reset_less=True)
        comb += pd44.eq(masked(r.pde[12:56], r.addr[12:56], finalmask))
        comb += pte.eq(Cat(r.pde[0:12], pd44))

        # update registers
        comb += rin.eq(v)

        # drive outputs
        with m.If(tlbie_req):
            comb += addr.eq(r.addr)
        with m.Elif(tlb_load):
            comb += addr.eq(Cat(C(0, 12), r.addr[12:64]))
            comb += tlb_data.eq(pte)
        with m.Elif(prtbl_rd):
            comb += addr.eq(prtb_adr)
        with m.Else():
            comb += addr.eq(pgtb_adr)

        comb += l_out.done.eq(r.done)
        comb += l_out.err.eq(r.err)
        comb += l_out.invalid.eq(r.invalid)
        comb += l_out.badtree.eq(r.badtree)
        comb += l_out.segerr.eq(r.segerror)
        comb += l_out.perm_error.eq(r.perm_err)
        comb += l_out.rc_error.eq(r.rc_error)

        comb += d_out.valid.eq(dcreq)
        comb += d_out.tlbie.eq(tlbie_req)
        comb += d_out.doall.eq(r.inval_all)
        comb += d_out.tlbld.eq(tlb_load)
        comb += d_out.addr.eq(addr)
        comb += d_out.pte.eq(tlb_data)

        comb += i_out.tlbld.eq(itlb_load)
        comb += i_out.tlbie.eq(tlbie_req)
        comb += i_out.doall.eq(r.inval_all)
        comb += i_out.addr.eq(addr)
        comb += i_out.pte.eq(tlb_data)

        return m

stop = False

def dcache_get(dut):
    """simulator process for getting memory load requests
    """

    global stop

    def b(x):
        return int.from_bytes(x.to_bytes(8, byteorder='little'),
                              byteorder='big', signed=False)

    mem = {0x0: 0x000000, # to get mtspr prtbl working

           0x10000:    # PARTITION_TABLE_2
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
            dc_valid = yield (dut.d_out.valid)
            if dc_valid:
                break
            yield
        addr = yield dut.d_out.addr
        if addr not in mem:
            print ("    DCACHE LOOKUP FAIL %x" % (addr))
            stop = True
            return

        yield
        data = mem[addr]
        yield dut.d_in.data.eq(data)
        print ("    DCACHE GET %x data %x" % (addr, data))
        yield dut.d_in.done.eq(1)
        yield
        yield dut.d_in.done.eq(0)

def mmu_wait(dut):
    global stop
    while not stop: # wait for dc_valid / err
        l_done = yield (dut.l_out.done)
        l_err = yield (dut.l_out.err)
        l_badtree = yield (dut.l_out.badtree)
        l_permerr = yield (dut.l_out.perm_error)
        l_rc_err = yield (dut.l_out.rc_error)
        l_segerr = yield (dut.l_out.segerr)
        l_invalid = yield (dut.l_out.invalid)
        if (l_done or l_err or l_badtree or
            l_permerr or l_rc_err or l_segerr or l_invalid):
            break
        yield
        yield dut.l_in.valid.eq(0) # data already in MMU by now
        yield dut.l_in.mtspr.eq(0) # captured by RegStage(s)
        yield dut.l_in.load.eq(0)  # can reset everything safely

def mmu_sim(dut):
    global stop

    # MMU MTSPR set prtbl
    yield dut.l_in.mtspr.eq(1)
    yield dut.l_in.sprn[9].eq(1) # totally fake way to set SPR=prtbl
    yield dut.l_in.rs.eq(0x1000000) # set process table
    yield dut.l_in.valid.eq(1)
    yield from mmu_wait(dut)
    yield
    yield dut.l_in.sprn.eq(0)
    yield dut.l_in.rs.eq(0)
    yield

    prtbl = yield (dut.rin.prtbl)
    print ("prtbl after MTSPR %x" % prtbl)
    assert prtbl == 0x1000000

    #yield dut.rin.prtbl.eq(0x1000000) # manually set process table
    #yield


    # MMU PTE request
    yield dut.l_in.load.eq(1)
    yield dut.l_in.priv.eq(1)
    yield dut.l_in.addr.eq(0x10000)
    yield dut.l_in.valid.eq(1)
    yield from mmu_wait(dut)

    addr = yield dut.d_out.addr
    pte = yield dut.d_out.pte
    l_done = yield (dut.l_out.done)
    l_err = yield (dut.l_out.err)
    l_badtree = yield (dut.l_out.badtree)
    print ("translated done %d err %d badtree %d addr %x pte %x" % \
               (l_done, l_err, l_badtree, addr, pte))
    yield
    yield dut.l_in.priv.eq(0)
    yield dut.l_in.addr.eq(0)


    stop = True


def test_mmu():
    dut = MMU()
    vl = rtlil.convert(dut, ports=[])#dut.ports())
    with open("test_mmu.il", "w") as f:
        f.write(vl)

    m = Module()
    m.submodules.mmu = dut

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(mmu_sim(dut)))
    sim.add_sync_process(wrap(dcache_get(dut)))
    with sim.write_vcd('test_mmu.vcd'):
        sim.run()

if __name__ == '__main__':
    test_mmu()
