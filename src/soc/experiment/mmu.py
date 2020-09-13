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
        pt_valid = Signal()
        pgtbl = Signal(64)
        rts = Signal(6)
        mbits = Signal(6)

        with m.If(~l_in.addr[63]):
            comb += pgtbl.eq(r.pgtbl0)
            comb += pt_valid.eq(r.pt0_valid)
        with m.Else():
            comb += pgtbl.eq(r.pt3_valid)
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

                with m.If(~mbits):
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
        comb += v.pde.eq(data)

        perm_ok = Signal()
        rc_ok = Signal()
        mbits = Signal(6)
        vbit = Signal(2)

        # test valid bit
        comb += vbit.eq(data[62:]) # leaf=data[62], valid=data[63]

        # valid & leaf
        with m.If(vbit == 0b11):
            # check permissions and RC bits
            with m.If(r.priv | ~data[3]):
                with m.If(~r.iside):
                    comb += perm_ok.eq(data[1:3].bool() & ~r.store)
                with m.Else():
                    # no IAMR, so no KUEP support for now
                    # deny execute permission if cache inhibited
                    comb += perm_ok.eq(data[0] & ~data[5])

            comb += rc_ok.eq(data[8] & (data[7] | (~r.store)))
            with m.If(perm_ok & rc_ok):
                comb += v.state.eq(State.RADIX_LOAD_TLB)
            with m.Else():
                comb += v.state.eq(State.RADIX_FINISH)
                comb += v.perm_err.eq(~perm_ok)
                # permission error takes precedence over RC error
                comb += v.rc_error.eq(perm_ok)

        # valid & !leaf
        with m.Elif(vbit == 0b10):
            comb += mbits.eq(data[0:5])
            with m.If((mbits < 5) | (mbits > 16) | (mbits > r.shift)):
                comb += v.state.eq(State.RADIX_FINISH)
                comb += v.badtree.eq(1)
            with m.Else():
                comb += v.shift.eq(v.shift - mbits)
                comb += v.mask_size.eq(mbits[0:5])
                comb += v.pgbase.eq(Cat(C(0, 8), data[8:56]))
                comb += v.state.eq(State.RADIX_LOOKUP)

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
            sync += Display(f"send load addr=%x addrsh=%d mask=%d",
                            d_out.addr, addrsh, mask)
        sync += r.eq(rin)

    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        addrsh = Signal(16)
        mask = Signal(16)
        finalmask = Signal(44)

        r = RegStage("r")
        rin = RegStage("r_in")

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
        pgtb_addr = Signal(64)
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
            sync += Display("MMU state %d", r.state)

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
                comb += dcreq.eq(1)
                comb += v.state.eq(State.RADIX_READ_WAIT)

            with m.Case(State.RADIX_READ_WAIT):
                with m.If(d_in.done):
                    self.radix_read_wait(m, v, r, d_in, data)
                with m.Else():
                    # non-present PTE, generate a DSI
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.invalid.eq(1)

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
        comb += pgtb_addr.eq(Cat(C(0, 3), pg16, r.pgbase[19:56]))

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
            comb += addr.eq(pgtb_addr)

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

    mem = {0x10000:             # PARTITION_TABLE_2
            0x800000000100000b, # PATB_GR=1 PRTB=0x1000 PRTS=0xb
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
        data = mem[addr]
        yield dut.d_in.data.eq(data)
        print ("dcache get %x data %x" % (addr, data))
        yield dut.d_in.done.eq(1)
        yield
        yield dut.d_in.done.eq(0)


def mmu_sim(dut):
    yield dut.l_in.load.eq(1)
    yield dut.l_in.addr.eq(0x10000)
    yield dut.l_in.valid.eq(1)
    while True: # wait for dc_valid
        d_valid = yield (dut.d_out.valid)
        if d_valid:
            break
        yield
    addr = yield dut.d_out.addr
    pte = yield dut.d_out.pte
    print ("translated addr %x pte %x" % (addr, pte))

    global stop
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
