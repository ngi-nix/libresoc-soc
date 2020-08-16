"""MMU

based on Anton Blanchard microwatt mmu.vhdl

"""
from enum import Enum, unique
from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl, Signal)
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
        comb += mask.eq(Const(0x001F, 16))

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

#               -- set v.shift to rts so that we can use finalmask
#               -- for the segment check
#               v.shift := rts;
#               v.mask_size := mbits(4 downto 0);
#               v.pgbase := pgtbl(55 downto 8) & x"00";
                # set v.shift to rts so that we can use finalmask
                # for the segment check
                comb += v.shift.eq(rts)
                comb += v.mask_size.eq(mbits[0:5])
                comb += v.pgbase.eq(pgtbl[8:56])

#               if l_in.valid = '1' then
                with m.If(l_in.valid):
#                   v.addr := l_in.addr;
#                   v.iside := l_in.iside;
#                   v.store := not (l_in.load or l_in.iside);
#                   v.priv := l_in.priv;
                    comb += v.addr.eq(l_in.addr)
                    comb += v.iside.eq(l_in.iside)
                    comb += v.store.eq(~(l_in.load | l_in.iside))
#                   if l_in.tlbie = '1' then
                    with m.If(l_in.tlbie):
#                       -- Invalidate all iTLB/dTLB entries for
#                       -- tlbie with RB[IS] != 0 or RB[AP] != 0,
#                       -- or for slbia
#                       v.inval_all := l_in.slbia or l_in.addr(11)
#                                      or l_in.addr(10) or
#                                      l_in.addr(7) or l_in.addr(6)
#                                      or l_in.addr(5);
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
#                       -- The RIC field of the tlbie instruction
#                       -- comes across on the sprn bus as bits 2--3.
#                       -- RIC=2 flushes process table caches.
#                       if l_in.sprn(3) = '1' then
                        # The RIC field of the tlbie instruction
                        # comes across on the sprn bus as bits 2--3.
                        # RIC=2 flushes process table caches.
                        with m.If(l_in.sprn[3]):
#                           v.pt0_valid := '0';
#                           v.pt3_valid := '0';
                            comb += v.pt0_valid.eq(0)
                            comb += v.pt3_valid.eq(0)
#                       end if;
#                       v.state := DO_TLBIE;
                        comb += v.state.eq(State.DO_TLBIE)
#                   else
                    with m.Else():
#                       v.valid := '1';
                        comb += v.valid.eq(1)
#                       if pt_valid = '0' then
                        with m.If(~pt_valid):
#                           -- need to fetch process table entry
#                           -- set v.shift so we can use finalmask
#                           -- for generating the process table
#                           -- entry address
#                           v.shift := unsigned('0' & r.prtbl(
#                                               4 downto 0));
#                           v.state := PROC_TBL_READ;
                            # need to fetch process table entry
                            # set v.shift so we can use finalmask
                            # for generating the process table
                            # entry address
                            comb += v.shift.eq(r.prtble[0:5])
                            comb += v.state.eq(State.PROC_TBL_READ)

#                       elsif mbits = 0 then
                        with m.If(~mbits):
#                           -- Use RPDS = 0 to disable radix
#                           -- tree walks
#                           v.state := RADIX_FINISH;
#                           v.invalid := '1';
                            # Use RPDS = 0 to disable radix
                            # tree walks
                            comb += v.state.eq(State.RADIX_FINISH)
                            comb += v.invalid.eq(1)
#                       else
                        with m.Else():
#                           v.state := SEGMENT_CHECK;
                            comb += v.state.eq(State.SEGMENT_CHECK)
#                       end if;
#                   end if;
#               end if;

#               if l_in.mtspr = '1' then
                with m.If(l_in.mtspr):
#                   -- Move to PID needs to invalidate L1 TLBs
#                   -- and cached pgtbl0 value.  Move to PRTBL
#                   -- does that plus invalidating the cached
#                   -- pgtbl3 value as well.
#                   if l_in.sprn(9) = '0' then
                    # Move to PID needs to invalidate L1 TLBs
                    # and cached pgtbl0 value.  Move to PRTBL
                    # does that plus invalidating the cached
                    # pgtbl3 value as well.
                    with m.If(~l_in.sprn[9]):
#                       v.pid := l_in.rs(31 downto 0);
                        comb += v.pid.eq(l_in.rs[0:32])
#                   else
                    with m.Else():
#                       v.prtbl := l_in.rs;
#                       v.pt3_valid := '0';
                        comb += v.prtbl.eq(l_in.rs)
                        comb += v.pt3_valid.eq(0)
#                   end if;

#                   v.pt0_valid := '0';
#                   v.inval_all := '1';
#                   v.state := DO_TLBIE;
                    comb += v.pt0_valid.eq(0)
                    comb += v.inval_all.eq(1)
                    comb += v.state.eq(State.DO_TLBIE)
#               end if;

#       when DO_TLBIE =>
            with m.Case(State.DO_TLBIE):
#               dcreq := '1';
#               tlbie_req := '1';
#               v.state := TLB_WAIT;
                comb += dcreq.eq(1)
                comb += tlbie_req.eq(1)
                comb += v.state.eq(State.TLB_WAIT)

#       when TLB_WAIT =>
            with m.Case(State.TLB_WAIT):
#               if d_in.done = '1' then
                with m.If(d_in.done):
#                   v.state := RADIX_FINISH;
                    comb += v.state.eq(State.RADIX_FINISH)
#               end if;

#       when PROC_TBL_READ =>
            with m.Case(State.PROC_TBL_READ):
#           dcreq := '1';
#           prtbl_rd := '1';
#           v.state := PROC_TBL_WAIT;
                comb += dcreq.eq(1)
                comb += prtbl_rd.eq(1)
                comb += v.state.eq(State.PROC_TBL_WAIT)

#       when PROC_TBL_WAIT =>
            with m.Case(State.PROC_TBL_WAIT):
#           if d_in.done = '1' then
                with m.If(d_in.done):
#               if r.addr(63) = '1' then
                    with m.If(r.addr[63]):
#                   v.pgtbl3 := data;
#                   v.pt3_valid := '1';
                        comb += v.pgtbl3.eq(data)
                        comb += v.pt3_valid.eq(1)
#                   else
                    with m.Else():
#                       v.pgtbl0 := data;
#                       v.pt0_valid := '1';
                        comb += v.pgtbl0.eq(data)
                        comb += v.pt0_valid.eq(1)
#                   end if;
#                   -- rts == radix tree size, # address bits
#                   -- being translated
#                   rts := unsigned('0' & data(62 downto 61) &
#                                   data(7 downto 5));
                    # rts == radix tree size, # address bits
                    # being translated
                    comb += rts.eq(Cat(data[5:8], data[61:63]))

#                   -- mbits == # address bits to index
#                   -- top level of tree
#                   mbits := unsigned('0' & data(4 downto 0));
                    # mbits == # address bits to index
                    # top level of tree
                    comb += mbits.eq(data[0:5])
#               -- set v.shift to rts so that we can use
#               -- finalmask for the segment check
#               v.shift := rts;
#               v.mask_size := mbits(4 downto 0);
#               v.pgbase := data(55 downto 8) & x"00";
                    # set v.shift to rts so that we can use
                    # finalmask for the segment check
                    comb += v.shift.eq(rts)
                    comb += v.mask_size.eq(mbits[0:5])
                    comb += v.pgbase.eq(data[8:56])

#                   if mbits = 0 then
                    with m.If(~mbits):
#                       v.state := RADIX_FINISH;
#                       v.invalid := '1';
                        comb += v.state.eq(State.RADIX_FINISH)
                        comb += v.invalid.eq(1)
#                   else
#                       v.state := SEGMENT_CHECK;
                        comb += v.state.eq(State.SEGMENT_CHECK)
#                   end if;
#               end if;

#               if d_in.err = '1' then
                with m.If(d_in.err):
#                   v.state := RADIX_FINISH;
#                   v.badtree := '1';
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)
#               end if;

#           when SEGMENT_CHECK =>
            with m.Case(State.SEGMENT_CHECK):
#               mbits := '0' & r.mask_size;
#               v.shift := r.shift + (31 - 12) - mbits;
#               nonzero := or(r.addr(61 downto 31) and
#                           not finalmask(30 downto 0));
                comb += mbits.eq(r.mask_size)
                comb += v.shift.eq(r.shift + (31 -12) - mbits)
                comb += nonzero.eq((
                         r.addr[31:62] & ~finalmask[0:31]
                        ).bool())
#               if r.addr(63) /= r.addr(62) or nonzero = '1' then
#                   v.state := RADIX_FINISH;
#                   v.segerror := '1';
                with m.If((r.addr[63] != r.addr[62])
                          | nonzero):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.segerror.eq(1)
#               elsif mbits < 5 or mbits > 16 or mbits
#                       > (r.shift + (31 - 12)) then
#                   v.state := RADIX_FINISH;
#                   v.badtree := '1';
                with m.If((mbits < 5) | (mbits > 16)
                          | (mbits > (r.shift + (31-12)))):
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)
#           else
#               v.state := RADIX_LOOKUP;
                with m.Else():
                    comb += v.state.eq(State.RADIX_LOOKUP)
#           end if;
#
#           when RADIX_LOOKUP =>
            with m.Case(State.RADIX_LOOKUP):
#               dcreq := '1';
#               v.state := RADIX_READ_WAIT;
                comb += dcreq.eq(1)
                comb += v.state.eq(State.RADIX_READ_WAIT)

#           when RADIX_READ_WAIT =>
            with m.Case(State.RADIX_READ_WAIT):
#               if d_in.done = '1' then
                with m.If(d_in.done):
#                   v.pde := data;
                    comb += v.pde.eq(data)
#                   -- test valid bit
#                   if data(63) = '1' then
                    # test valid bit
                    with m.If(data[63]):
#                       -- test leaf bit
#                       if data(62) = '1' then
                        # test leaf bit
                        with m.If(data[62]):
#                           -- check permissions and RC bits
#                           perm_ok := '0';
                            comb += perm_ok.eq(0)
#                           if r.priv = '1' or data(3) = '0' then
                            with m.If(r.priv | ~data[3]):
#                               if r.iside = '0' then
#                                   perm_ok := data(1) or (data(2)
#                                              and not r.store);
                                with m.If(~r.iside):
                                    comb += perm_ok.eq(
                                             (data[1] | data[2])
                                             & (~r.store)
                                            )
#                               else
                                with m.Else():
#                                   -- no IAMR, so no KUEP support
#                                   -- for now deny execute
#                                   -- permission if cache inhibited
#                                   perm_ok :=
#                                       data(0) and not data(5);
                                    # no IAMR, so no KUEP support
                                    # for now deny execute
                                    # permission if cache inhibited
                                    comb += perm_ok.eq(
                                              data[0] & ~data[5]
                                            )
#                               end if;
#                           end if;

#                           rc_ok := data(8) and (data(7) or
#                                    not r.store);
                            comb += rc_ok.eq(
                                     data[8] &
                                     (data[7] | (~r.store))
                                    )
#                           if perm_ok = '1' and rc_ok = '1' then
#                               v.state := RADIX_LOAD_TLB;
                            with m.If(perm_ok & rc_ok):
                                comb += v.state.eq(
                                         State.RADIX_LOAD_TLB
                                        )
#                           else
                            with m.Else():
#                           v.state := RADIX_FINISH;
#                           v.perm_err := not perm_ok;
#                           -- permission error takes precedence
#                           -- over RC error
#                               v.rc_error := perm_ok;
                                comb += vl.state.eq(
                                         State.RADIX_FINISH
                                        )
                                comb += v.perm_err.eq(~perm_ok)
                                # permission error takes precedence
                                # over RC error
                                comb += v.rc_error.eq(perm_ok)
#                           end if;
#                       else
                        with m.Else():
#                           mbits := unsigned('0' &
#                                    data(4 downto 0));
                            comb += mbits.eq(data[0:5])
#                           if mbits < 5 or mbits > 16 or
#                           mbits > r.shift then
#                               v.state := RADIX_FINISH;
#                               v.badtree := '1';
                            with m.If((mbits < 5) | (mbits > 16) |
                                      (mbits > r.shift)):
                                comb += v.state.eq(
                                          State.RADIX_FINISH
                                        )
                                comb += v.badtree.eq(1)
#                           else
                            with m.Else():
#                               v.shift := v.shift - mbits;
#                               v.mask_size := mbits(4 downto 0);
#                               v.pgbase := data(55 downto 8)
#                                           & x"00";
#                               v.state := RADIX_LOOKUP;
                                comb += v.shift.eq(v.shif - mbits)
                                comb += v.mask_size.eq(mbits[0:5])
                                comb += v.pgbase.eq(mbits[8:56])
                                comb += v.state.eq(
                                         State.RADIX_LOOKUP
                                        )
#                           end if;
#                       end if;
#                   else
                    with m.Else():
#                       -- non-present PTE, generate a DSI
#                       v.state := RADIX_FINISH;
#                       v.invalid := '1';
                        # non-present PTE, generate a DSI
                        comb += v.state.eq(State.RADIX_FINISH)
                        comb += v.invalid.eq(1)
#                   end if;
#               end if;

#               if d_in.err = '1' then
                with m.If(d_in.err):
#                   v.state := RADIX_FINISH;
#                   v.badtree := '1';
                    comb += v.state.eq(State.RADIX_FINISH)
                    comb += v.badtree.eq(1)
#               end if;

#           when RADIX_LOAD_TLB =>
            with m.Case(State.RADIX_LOAD_TLB):
#               tlb_load := '1';
                comb +=  tlb_load.eq(1)
#               if r.iside = '0' then
                with m.If(~r.iside):
#                   dcreq := '1';
#                   v.state := TLB_WAIT;
                    comb += dcreq.eq(1)
                    comb += v.state.eq(State.TLB_WAIT)
#               else
                with m.Else():
#                   itlb_load := '1';
#                   v.state := IDLE;
                    comb += itlb_load.eq(1)
                    comb += v.state.eq(State.IDLE)
#               end if;

#           when RADIX_FINISH =>
#               v.state := IDLE;
            with m.Case(State.RADIX_FINISH):
#               v.state := IDLE
                comb += v.state.eq(State.IDLE)
#       end case;
#
#       if v.state = RADIX_FINISH or (v.state = RADIX_LOAD_TLB
#       and r.iside = '1') then
        with m.If((v.state == State.RADIX_FINISH)
                  | (v.state == State.RADIX_LOAD_TLB & r.iside)
                 ):
#           v.err := v.invalid or v.badtree or v.segerror
#                    or v.perm_err or v.rc_error;
#           v.done := not v.err;
            comb += v.err.eq(v.invalid | v.badtree | v.segerror
                             | v.perm_err | v.rc_error)
            comb += v.done.eq(~v.err)
#       end if;

#       if r.addr(63) = '1' then
        with m.If(r.addr[63]):
#           effpid := x"00000000";
            comb += effpid.eq(Const(0x00000000, 32))
#       else
        with m.Else():
#           effpid := r.pid;
            comb += effpid.eq(r.pid)
#       end if;
#       prtable_addr := x"00" & r.prtbl(55 downto 36) &
#                       ((r.prtbl(35 downto 12) and not finalmask(
#                       23 downto 0)) or (effpid(31 downto 8) and
#                       finalmask(23 downto 0))) & effpid(7 downto 0)
#                       & "0000";
        comb += prtable_addr.eq(Cat(
                 Const(0b0000, 4), effpid[0:8],
                 (
                  (r.prtble[12:36] & ~finalmask[0:24])
                  | effpid[8:32]   &  finalmask[0:24]
                 ),
                 r.prtbl[36:56]
                ))

#       pgtable_addr := x"00" & r.pgbase(55 downto 19) &
#                       ((r.pgbase(18 downto 3) and not mask) or
#                       (addrsh and mask)) & "000";
        comb += pgtable_addr.eq(Cat(
                 Const(0b000, 3),
                 (
                  (r.pgbase[3:19] & ~mask)
                  | (addrsh       &  mask)
                 ),
                 r.pgbase[19:56]
                ))

#       pte := x"00" & ((r.pde(55 downto 12) and not finalmask) or
#              (r.addr(55 downto 12) and finalmask)) & r.pde(11 downto 0);
        comb += pte.eq(Cat(
                 r.pde[0:12],
                 (
                  (r.pde[12:56]    & ~finalmask)
                  | (r.addr[12:56] &  finalmask)
                 ),
                ))

#       -- update registers
#       rin <= v;
        # update registers
        rin.eq(v)

#       -- drive outputs
#       if tlbie_req = '1' then
        # drive outputs
        with m.If(tlbie_req):
#           addr := r.addr;
#           tlb_data := (others => '0');
            comb += addr.eq(r.addr)
            comb += tlb_data.eq(0)
#       elsif tlb_load = '1' then
        with m.If(tlb_load):
#           addr := r.addr(63 downto 12) & x"000";
#           tlb_data := pte;
            comb += addr.eq(r.addr[12:64])
            comb += tlb_data.eq(pte)
#       elsif prtbl_rd = '1' then
        with m.If(prtbl_rd):
#           addr := prtable_addr;
#           tlb_data := (others => '0');
            comb += addr.eq(prtable_addr)
            comb += tlb_data.eq(0)
#       else
        with m.Else():
#           addr := pgtable_addr;
#           tlb_data := (others => '0');
            comb += addr.eq(pgtable_addr)
            comb += tlb_data.eq(0)
#       end if;

#       l_out.done <= r.done;
#       l_out.err <= r.err;
#       l_out.invalid <= r.invalid;
#       l_out.badtree <= r.badtree;
#       l_out.segerr <= r.segerror;
#       l_out.perm_error <= r.perm_err;
#       l_out.rc_error <= r.rc_error;
        comb += l_out.done.eq(r.done)
        comb += l_out.err.eq(r.err)
        comb += l_out.invalid.eq(r.invalid)
        comb += l_out.badtree.eq(r.badtree)
        comb += l_out.segerr.eq(r.segerror)
        comb += l_out.perm_error.eq(r.perm_err)
        comb += l_out.rc_error.eq(r.rc_error)

#       d_out.valid <= dcreq;
#       d_out.tlbie <= tlbie_req;
#       d_out.doall <= r.inval_all;
#       d_out.tlbld <= tlb_load;
#       d_out.addr <= addr;
#       d_out.pte <= tlb_data;
        comb += d_out.valid.eq(dcreq)
        comb += d_out.tlbie.eq(tlbie_req)
        comb += d_out.doall.eq(r.inval_all)
        comb += d_out.tlbld.eeq(tlb_load)
        comb += d_out.addr.eq(addr)
        comb += d_out.pte.eq(tlb_data)

#       i_out.tlbld <= itlb_load;
#       i_out.tlbie <= tlbie_req;
#       i_out.doall <= r.inval_all;
#       i_out.addr <= addr;
#       i_out.pte <= tlb_data;
        comb += i_out.tlbld.eq(itlb_load)
        comb += i_out.tblie.eq(tlbie_req)
        comb += i_out.doall.eq(r.inval_all)
        comb += i_out.addr.eq(addr)
        comb += i_out.pte.eq(tlb_data)

#   end process;
# end;


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
