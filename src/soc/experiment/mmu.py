"""MMU

based on Anton Blanchard microwatt mmu.vhdl

"""
from enum import Enum, unique
from nmigen import (C, Module, Signal, Elaboratable, Mux, Cat, Repl, Signal)
from nmigen.cli import main
from nmutil.iocontrol import RecordObject
from nmutil.byterev import byte_reverse

from soc.experiment.mem_types import (LoadStore1ToMmuType,
                                 MmuToLoadStore1Type,
                                 MmuToDcacheType,
                                 DcacheToMmuType,
                                 MmuToIcacheType)

# -- Radix MMU
# -- Supports 4-level trees as in arch 3.0B, but not the
# -- two-step translation
# -- for guests under a hypervisor (i.e. there is no gRA -> hRA translation).

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


# -- generate mask for extracting address fields for PTE address
# -- generation
# addrmaskgen: process(all)
# generate mask for extracting address fields for PTE address
# generation
class AddrMaskGen(Elaboratable):
    def __init__(self):
#       variable m : std_ulogic_vector(15 downto 0);
        super().__init__()
        self.msk = Signal(16)

#   begin
    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        rst = ResetSignal()

        msk = self.msk

        r    = self.r
        mask = self.mask

#       -- mask_count has to be >= 5
#       m := x"001f";
        # mask_count has to be >= 5
        comb += mask.eq(C(0x001F, 16))

#       for i in 5 to 15 loop
        for i in range(5,16):
#           if i < to_integer(r.mask_size) then
            with m.If(i < r.mask_size):
#               m(i) := '1';
                comb += msk[i].eq(1)
#           end if;
#       end loop;
#       mask <= m;
        comb += mask.eq(msk)
#   end process;

# -- generate mask for extracting address bits to go in
# -- TLB entry in order to support pages > 4kB
# finalmaskgen: process(all)
# generate mask for extracting address bits to go in
# TLB entry in order to support pages > 4kB
class FinalMaskGen(Elaboratable):
    def __init__(self):
#       variable m : std_ulogic_vector(43 downto 0);
        super().__init__()
        self.msk = Signal(44)

#   begin
    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        rst = ResetSignal()

        mask = self.mask
        r    = self.r

        msk = self.msk

#       for i in 0 to 43 loop
        for i in range(44):
#           if i < to_integer(r.shift) then
            with m.If(i < r.shift):
#               m(i) := '1';
                comb += msk.eq(1)
#           end if;
#       end loop;
#       finalmask <= m;
        comb += self.finalmask(mask)
#   end process;


class RegStage(RecordObject):
    def __init__(self, name=None):
        super().__init__(self, name=name)
        # latched request from loadstore1
        self.valid = Signal(reset_less=True)
        self.iside = Signal(reset_less=True)
        self.store = Signal(reset_less=True)
        self.priv = Signal(reset_less=True)
        self.addr = Signal(64, reset_less=True)
        self.inval_all = Signal(reset_less=True)
        # config SPRs
        self.prtbl = Signal(64, reset_less=True)
        self.pid = Signal(32, reset_less=True)
        # internal state
        self.state = State.IDLE
        self.done = Signal(reset_less=True)
        self.err = Signal(reset_less=True)
        self.pgtbl0 = Signal(64, reset_less=True)
        self.pt0_valid = Signal(reset_less=True)
        self.pgtbl3 = Signal(64, reset_less=True)
        self.pt3_valid = Signal(reset_less=True)
        self.shift = Signal(6, reset_less=True)
        self.mask_size = Signal(5, reset_less=True)
        self.pgbase = Signal(56, reset_less=True)
        self.pde = Signal(64, reset_less=True)
        self.invalid = Signal(reset_less=True)
        self.badtree = Signal(reset_less=True)
        self.segerror = Signal(reset_less=True)
        self.perm_err = Signal(reset_less=True)
        self.rc_error = Signal(reset_less=True)


class MMU(Elaboratable):
    """Radix MMU

    Supports 4-level trees as in arch 3.0B, but not the
    two-step translation for guests under a hypervisor
    (i.e. there is no gRA -> hRA translation).
    """
    def __init__(self):
        self.l_in  = LoadStore1ToMmuType()
        self.l_out = MmuToLoadStore1Type()
        self.d_out = MmuToDcacheType()
        self.d_in  = DcacheToMmuType()
        self.i_out = MmuToIcacheType()

    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        addrsh = Signal(16)
        mask = Signal(16)
        finalmask = Signal(44)

        r = RegStage()
        rin = RegStage()

        l_in  = self.l_in
        l_out = self.l_out
        d_out = self.d_out
        d_in  = self.d_in
        i_out = self.i_out

        # Multiplex internal SPR values back to loadstore1,
        # selected by l_in.sprn.
        with m.If(l_in.sprn[9]):
            comb += l_out.sprval.eq(r.prtbl)
        with m.Else():
            comb += l_out.sprval.eq(r.pid)

        with m.If(rin.valid):
            pass
            #sync += Display(f"MMU got tlb miss for {rin.addr}")

        with m.If(l_out.done):
            pass
            # sync += Display("MMU completing op without error")

        with m.If(l_out.err):
            pass
            # sync += Display(f"MMU completing op with err invalid"
            #                 "{l_out.invalid} badtree={l_out.badtree}")

        with m.If(rin.state == State.RADIX_LOOKUP):
            pass
            # sync += Display (f"radix lookup shift={rin.shift}"
            #          "msize={rin.mask_size}")

        with m.If(r.state == State.RADIX_LOOKUP):
            pass
            # sync += Display(f"send load addr={d_out.addr}"
            #           "addrsh={addrsh} mask={mask}")

        sync += r.eq(rin)

        v = RegStage()
        dcrq = Signal()
        tlb_load = Signal()
        itlb_load = Signal()
        tlbie_req = Signal()
        prtbl_rd = Signal()
        pt_valid = Signal()
        effpid = Signal(32)
        prtable_addr = Signal(64)
        rts = Signal(6)
        mbits = Signal(6)
        pgtable_addr = Signal(64)
        pte = Signal(64)
        tlb_data = Signal(64)
        nonzero = Signal()
        pgtbl = Signal(64)
        perm_ok = Signal()
        rc_ok = Signal()
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

        with m.Switch(r.state):
            with m.Case(State.IDLE):
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
                            comb += v.shift.eq(r.prtble[0:5])
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
                    with m.If(r.addr[63]):
                        comb += v.pgtbl3.eq(data)
                        comb += v.pt3_valid.eq(1)
                    with m.Else():
                        comb += v.pgtbl0.eq(data)
                        comb += v.pt0_valid.eq(1)
                    # rts == radix tree size, # address bits being translated
                    comb += rts.eq(Cat(data[5:8], data[61:63]))

                    # mbits == # address bits to index top level of tree
                    comb += mbits.eq(data[0:5])
                    # set v.shift to rts so that we can use
                    # finalmask for the segment check
                    comb += v.shift.eq(rts)
                    comb += v.mask_size.eq(mbits[0:5])
                    comb += v.pgbase.eq(Cat(C(0, 8), data[8:56]))

                    with m.If(~mbits):
                        comb += v.state.eq(State.RADIX_FINISH)
                        comb += v.invalid.eq(1)
                        comb += v.state.eq(State.SEGMENT_CHECK)

                with m.If(d_in.err):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)

            with m.Case(State.SEGMENT_CHECK):
                comb += mbits.eq(r.mask_size)
                comb += v.shift.eq(r.shift + (31 - 12) - mbits)
                comb += nonzero.eq((r.addr[31:62] & ~finalmask[0:31]).bool())
                with m.If((r.addr[63] ^ r.addr[62]) | nonzero):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.segerror.eq(1)
                with m.Elif((mbits < 5) | (mbits > 16)
                          | (mbits > (r.shift + (31-12)))):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)
                with m.Else():
                    comb += v.state.eq(State.RADIX_LOOKUP)

            with m.Case(State.RADIX_LOOKUP):
                comb += dcreq.eq(1)
                comb += v.state.eq(State.RADIX_READ_WAIT)

            with m.Case(State.RADIX_READ_WAIT):
                with m.If(d_in.done):
                    comb += v.pde.eq(data)
                    # test valid bit
                    with m.If(data[63]):
                        with m.If(data[62]):
                            # check permissions and RC bits
                            comb += perm_ok.eq(0)
                            with m.If(r.priv | ~data[3]):
                                with m.If(~r.iside):
                                    comb += perm_ok.eq((data[1] | data[2]) &
                                                       (~r.store))
                                with m.Else():
                                    # no IAMR, so no KUEP support
                                    # for now deny execute
                                    # permission if cache inhibited
                                    comb += perm_ok.eq(data[0] & ~data[5])

                            comb += rc_ok.eq(data[8] & (data[7] | (~r.store)))
                            with m.If(perm_ok & rc_ok):
                                comb += v.state.eq(State.RADIX_LOAD_TLB)
                            with m.Else():
                                comb += vl.state.eq(State.RADIX_ERROR)
                                comb += v.perm_err.eq(~perm_ok)
                                # permission error takes precedence
                                # over RC error
                                comb += v.rc_error.eq(perm_ok)
                        with m.Else():
                            comb += mbits.eq(data[0:5])
                            with m.If((mbits < 5) | (mbits > 16) |
                                      (mbits > r.shift)):
                                comb += v.state.eq(State.RADIX_FINISH)
                                comb += v.badtree.eq(1)
                            with m.Else():
                                comb += v.shift.eq(v.shif - mbits)
                                comb += v.mask_size.eq(mbits[0:5])
                                comb += v.pgbase.eq(Cat(C(0, 8), data[8:56]))
                                comb += v.state.eq(State.RADIX_LOOKUP)
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

        with m.If((v.state == State.RADIX_FINISH)
                  | ((v.state == State.RADIX_LOAD_TLB) & r.iside)):
            comb += v.err.eq(v.invalid | v.badtree | v.segerror
                             | v.perm_err | v.rc_error)
            comb += v.done.eq(~v.err)

        with m.If(~r.addr[63]):
            comb += effpid.eq(r.pid)

        comb += prtable_addr.eq(Cat(
                                 C(0b0000, 4),
                                 effpid[0:8],
                                 (r.prtble[12:36] & ~finalmask[0:24]) |
                                 (effpid[8:32]    &  finalmask[0:24]),
                                 r.prtbl[36:56]
                                ))

        comb += pgtable_addr.eq(Cat(
                                 C(0b000, 3),
                                 (r.pgbase[3:19] & ~mask) |
                                 (addrsh         &  mask),
                                 r.pgbase[19:56]
                                ))

        comb += pte.eq(Cat(
                         r.pde[0:12],
                          (r.pde[12:56]    & ~finalmask) |
                          (r.addr[12:56] &  finalmask),
                        ))

        # update registers
        rin.eq(v)

        # drive outputs
        with m.If(tlbie_req):
            comb += addr.eq(r.addr)
        with m.Elif(tlb_load):
            comb += addr.eq(Cat(C(0, 12), r.addr[12:64]))
            comb += tlb_data.eq(pte)
        with m.Elif(prtbl_rd):
            comb += addr.eq(prtable_addr)
        with m.Else():
            comb += addr.eq(pgtable_addr)

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
        comb += d_out.tlbld.eeq(tlb_load)
        comb += d_out.addr.eq(addr)
        comb += d_out.pte.eq(tlb_data)

        comb += i_out.tlbld.eq(itlb_load)
        comb += i_out.tblie.eq(tlbie_req)
        comb += i_out.doall.eq(r.inval_all)
        comb += i_out.addr.eq(addr)
        comb += i_out.pte.eq(tlb_data)


def mmu_sim():
    yield wp.waddr.eq(1)
    yield wp.data_i.eq(2)
    yield wp.wen.eq(1)
    yield
    yield wp.wen.eq(0)
    yield rp.ren.eq(1)
    yield rp.raddr.eq(1)
    yield Settle()
    data = yield rp.data_o
    print(data)
    assert data == 2
    yield

    yield wp.waddr.eq(5)
    yield rp.raddr.eq(5)
    yield rp.ren.eq(1)
    yield wp.wen.eq(1)
    yield wp.data_i.eq(6)
    yield Settle()
    data = yield rp.data_o
    print(data)
    assert data == 6
    yield
    yield wp.wen.eq(0)
    yield rp.ren.eq(0)
    yield Settle()
    data = yield rp.data_o
    print(data)
    assert data == 0
    yield
    data = yield rp.data_o
    print(data)

def test_mmu():
    dut = MMU()
    rp = dut.read_port()
    wp = dut.write_port()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_mmu.il", "w") as f:
        f.write(vl)

    run_simulation(dut, mmu_sim(), vcd_name='test_mmu.vcd')

if __name__ == '__main__':
    test_mmu()
