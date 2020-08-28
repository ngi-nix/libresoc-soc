"""Dcache

based on Anton Blanchard microwatt dcache.vhdl

"""

from enum import Enum, unique

from nmigen import Module, Signal, Elaboratable,
                   Cat, Repl
from nmigen.cli import main
from nmigen.iocontrol import RecordObject
from nmigen.util import log2_int

from experiment.mem_types import LoadStore1ToDcacheType,
                                 DcacheToLoadStore1Type,
                                 MmuToDcacheType,
                                 DcacheToMmuType

from experiment.wb_types import WB_ADDR_BITS, WB_DATA_BITS, WB_SEL_BITS,
                                WBAddrType, WBDataType, WBSelType,
                                WbMasterOut, WBSlaveOut,
                                WBMasterOutVector, WBSlaveOutVector,
                                WBIOMasterOut, WBIOSlaveOut


# Record for storing permission, attribute, etc. bits from a PTE
class PermAttr(RecordObject):
    def __init__(self):
        super().__init__()
        self.reference = Signal()
        self.changed   = Signal()
        self.nocache   = Signal()
        self.priv      = Signal()
        self.rd_perm   = Signal()
        self.wr_perm   = Signal()


def extract_perm_attr(pte):
    pa = PermAttr()
    pa.reference = pte[8]
    pa.changed   = pte[7]
    pa.nocache   = pte[5]
    pa.priv      = pte[3]
    pa.rd_perm   = pte[2]
    pa.wr_perm   = pte[1]
    return pa;


# Type of operation on a "valid" input
@unique
class Op(Enum):
    OP_NONE       = 0
    OP_BAD        = 1 # NC cache hit, TLB miss, prot/RC failure
    OP_STCX_FAIL  = 2 # conditional store w/o reservation
    OP_LOAD_HIT   = 3 # Cache hit on load
    OP_LOAD_MISS  = 4 # Load missing cache
    OP_LOAD_NC    = 5 # Non-cachable load
    OP_STORE_HIT  = 6 # Store hitting cache
    OP_STORE_MISS = 7 # Store missing cache


# Cache state machine
@unique
class State(Enum):
    IDLE             = 0 # Normal load hit processing
    RELOAD_WAIT_ACK  = 1 # Cache reload wait ack
    STORE_WAIT_ACK   = 2 # Store wait ack
    NC_LOAD_WAIT_ACK = 3 # Non-cachable load wait ack


# Dcache operations:
#
# In order to make timing, we use the BRAMs with
# an output buffer, which means that the BRAM
# output is delayed by an extra cycle.
#
# Thus, the dcache has a 2-stage internal pipeline
# for cache hits with no stalls.
#
# All other operations are handled via stalling
# in the first stage.
#
# The second stage can thus complete a hit at the same
# time as the first stage emits a stall for a complex op.
#
# Stage 0 register, basically contains just the latched request
class RegStage0(RecordObject):
    def __init__(self):
        super().__init__()
        self.req     = LoadStore1ToDcacheType()
        self.tlbie   = Signal()
        self.doall   = Signal()
        self.tlbld   = Signal()
        self.mmu_req = Signal() # indicates source of request


class MemAccessRequest(RecordObject):
    def __init__(self):
        super().__init__()
        self.op        = Op()
        self.valid     = Signal()
        self.dcbz      = Signal()
        self.real_addr = Signal(REAL_ADDR_BITS)
        self.data      = Signal(64)
        self.byte_sel  = Signal(8)
        self.hit_way   = Signal(WAY_BITS)
        self.same_tag  = Signal()
        self.mmu_req   = Signal()


# First stage register, contains state for stage 1 of load hits
# and for the state machine used by all other operations
class RegStage1(RecordObject):
    def __init__(self):
        super().__init__()
        # Info about the request
        self.full             = Signal() # have uncompleted request
        self.mmu_req          = Signal() # request is from MMU
        self.req              = MemAccessRequest()

        # Cache hit state
        self.hit_way          = Signal(WAY_BITS)
        self.hit_load_valid   = Signal()
        self.hit_index        = Signal(NUM_LINES)
        self.cache_hit        = Signal()

        # TLB hit state
        self.tlb_hit          = Signal()
        self.tlb_hit_way      = Signal(TLB_NUM_WAYS)
        self.tlb_hit_index    = Signal(TLB_SET_SIZE)
        self.
        # 2-stage data buffer for data forwarded from writes to reads
        self.forward_data1    = Signal(64)
        self.forward_data2    = Signal(64)
        self.forward_sel1     = Signal(8)
        self.forward_valid1   = Signal()
        self.forward_way1     = Signal(WAY_BITS)
        self.forward_row1     = Signal(BRAM_ROWS)
        self.use_forward1     = Signal()
        self.forward_sel      = Signal(8)

        # Cache miss state (reload state machine)
        self.state            = State()
        self.dcbz             = Signal()
        self.write_bram       = Signal()
        self.write_tag        = Signal()
        self.slow_valid       = Signal()
        self.wb               = WishboneMasterOut()
        self.reload_tag       = Signal(TAG_BITS)
        self.store_way        = Signal(WAY_BITS)
        self.store_row        = Signal(BRAM_ROWS)
        self.store_index      = Signal(NUM_LINES)
        self.end_row_ix       = Signal(ROW_LINE_BIT)
        self.rows_valid       = RowPerLineValidArray()
        self.acks_pending     = Signal(3)
        self.inc_acks         = Signal()
        self.dec_acks         = Signal()

        # Signals to complete (possibly with error)
        self.ls_valid         = Signal()
        self.ls_error         = Signal()
        self.mmu_done         = Signal()
        self.mmu_error        = Signal()
        self.cache_paradox    = Signal()

        # Signal to complete a failed stcx.
        self.stcx_fail        = Signal()


# Reservation information
class Reservation(RecordObject):
    def __init__(self):
        super().__init__()
        valid = Signal()
        # TODO LINE_OFF_BITS is 6
        addr  = Signal(63 downto LINE_OFF_BITS)


# Set associative dcache write-through
#
# TODO (in no specific order):
#
# * See list in icache.vhdl
# * Complete load misses on the cycle when WB data comes instead of
#   at the end of line (this requires dealing with requests coming in
#   while not idle...)
class Dcache(Elaboratable):
    def __init__(self):
        # TODO: make these parameters of Dcache at some point
        self.LINE_SIZE = 64    # Line size in bytes
        self.NUM_LINES = 32    # Number of lines in a set
        self.NUM_WAYS = 4      # Number of ways
        self.TLB_SET_SIZE = 64 # L1 DTLB entries per set
        self.TLB_NUM_WAYS = 2  # L1 DTLB number of sets
        self.TLB_LG_PGSZ = 12  # L1 DTLB log_2(page_size)
        self.LOG_LENGTH = 0    # Non-zero to enable log data collection

        self.d_in      = LoadStore1ToDcacheType()
        self.d_out     = DcacheToLoadStore1Type()

        self.m_in      = MmuToDcacheType()
        self.m_out     = DcacheToMmuType()

        self.stall_out = Signal()

        self.wb_out    = WBMasterOut()
        self.wb_in     = WBSlaveOut()

        self.log_out   = Signal(20)

    # Latch the request in r0.req as long as we're not stalling
    def stage_0(self, m, d_in, m_in):
            comb = m.d.comb
            sync = m.d.sync

    #         variable r : reg_stage_0_t;
            r = RegStage0()
            comb += r

    #     begin
    #         if rising_edge(clk) then
    #             assert (d_in.valid and m_in.valid) = '0'
    #              report "request collision loadstore vs MMU";
            assert ~(d_in.valid & m_in.valid) "request collision
             loadstore vs MMU"

    #             if m_in.valid = '1' then
            with m.If(m_in.valid):
    #                 r.req.valid := '1';
    #                 r.req.load := not (m_in.tlbie or m_in.tlbld);
    #                 r.req.dcbz := '0';
    #                 r.req.nc := '0';
    #                 r.req.reserve := '0';
    #                 r.req.virt_mode := '0';
    #                 r.req.priv_mode := '1';
    #                 r.req.addr := m_in.addr;
    #                 r.req.data := m_in.pte;
    #                 r.req.byte_sel := (others => '1');
    #                 r.tlbie := m_in.tlbie;
    #                 r.doall := m_in.doall;
    #                 r.tlbld := m_in.tlbld;
    #                 r.mmu_req := '1';
                sync += r.req.valid.eq(1)
                sync += r.req.load.eq(~(m_in.tlbie | m_in.tlbld))
                sync += r.req.priv_mode.eq(1)
                sync += r.req.addr.eq(m_in.addr)
                sync += r.req.data.eq(m_in.pte)
                sync += r.req.byte_sel.eq(1)
                sync += r.tlbie.eq(m_in.tlbie)
                sync += r.doall.eq(m_in.doall)
                sync += r.tlbld.eq(m_in.tlbld)
                sync += r.mmu_req.eq(1)
    #             else
            with m.Else():
    #                 r.req := d_in;
    #                 r.tlbie := '0';
    #                 r.doall := '0';
    #                 r.tlbld := '0';
    #                 r.mmu_req := '0';
                sync += r.req.eq(d_in)
    #             end if;
    #             if rst = '1' then
    #                 r0_full <= '0';
    #             elsif r1.full = '0' or r0_full = '0' then
                with m.If(~r1.full | ~r0_full):
    #                 r0 <= r;
    #                 r0_full <= r.req.valid;
                    sync += r0.eq(r)
                    sync += r0_full.eq(r.req.valid)
    #             end if;
    #         end if;
    #     end process;

    # TLB
    # Operates in the second cycle on the request latched in r0.req.
    # TLB updates write the entry at the end of the second cycle.
    def tlb_read(self, m, m_in, d_in, r0_stall, tlb_valid_way,
                 tlb_tag_way, tlb_pte_way, dtlb_valid_bits,
                 dtlb_tags, dtlb_ptes):

        comb = m.d.comb
        sync = m.d.sync

    #         variable index : tlb_index_t;
    #         variable addrbits :
    #          std_ulogic_vector(TLB_SET_BITS - 1 downto 0);
        index    = TLB_SET_SIZE
        addrbits = Signal(TLB_SET_BITS)

        comb += index
        comb += addrbits

    #     begin
    #         if rising_edge(clk) then
    #             if m_in.valid = '1' then
        with m.If(m_in.valid):
    #                 addrbits := m_in.addr(TLB_LG_PGSZ + TLB_SET_BITS
    #                                       - 1 downto TLB_LG_PGSZ);
            sync += addrbits.eq(m_in.addr[
                     TLB_LG_PGSZ:TLB_LG_PGSZ + TLB_SET_BITS
                    ])
    #             else
        with m.Else():
    #                 addrbits := d_in.addr(TLB_LG_PGSZ + TLB_SET_BITS
    #                                       - 1 downto TLB_LG_PGSZ);
            sync += addrbits.eq(d_in.addr[
                     TLB_LG_PGSZ:TLB_LG_PGSZ + TLB_SET_BITS
                    ])
    #             end if;

    #             index := to_integer(unsigned(addrbits));
        sync += index.eq(addrbits)
    #             -- If we have any op and the previous op isn't
    #             -- finished, then keep the same output for next cycle.
    #             if r0_stall = '0' then
    # If we have any op and the previous op isn't finished,
    # then keep the same output for next cycle.
        with m.If(~r0_stall):
            sync += tlb_valid_way.eq(dtlb_valid_bits[index])
            sync += tlb_tag_way.eq(dtlb_tags[index])
            sync += tlb_pte_way.eq(dtlb_ptes[index])
    #             end if;
    #         end if;
    #     end process;

    #     -- Generate TLB PLRUs
    #     maybe_tlb_plrus: if TLB_NUM_WAYS > 1 generate
    # Generate TLB PLRUs
    def maybe_tlb_plrus(self, m, r1, tlb_plru_victim, acc, acc_en, lru):
            comb = m.d.comb
            sync = m.d.sync

            with m.If(TLB_NUM_WAYS > 1):
                for i in range(TLB_SET_SIZE):
                    # TLB PLRU interface
                    tlb_plru        = PLRU(TLB_WAY_BITS)
                    tlb_plru_acc    = Signal(TLB_WAY_BITS)
                    tlb_plru_acc_en = Signal()
                    tlb_plru_out    = Signal(TLB_WAY_BITS)

                    comb += tlb_plru.acc.eq(tlb_plru_acc)
                    comb += tlb_plru.acc_en.eq(tlb_plru_acc_en)
                    comb += tlb_plru.lru.eq(tlb_plru_out)

                    # PLRU interface
                    with m.If(r1.tlb_hit_index == i):
                        comb += tlb_plru.acc_en.eq(
                                 r1.tlb_hit
                                )

                    with m.Else():
                        comb += tlb_plru.acc_en.eq(0)
                    comb += tlb_plru.acc.eq(
                             r1.tlb_hit_way
                            )

                    comb += tlb_plru_victim[i].eq(tlb_plru.lru)

    def tlb_search(self, tlb_req_index, r0, tlb_valid_way_ tlb_tag_way,
                   tlb_pte_way, pte, tlb_hit, valid_ra, perm_attr, ra):

        comb = m.d.comb
        sync = m.d.sync

#         variable hitway : tlb_way_t;
#         variable hit : std_ulogic;
#         variable eatag : tlb_tag_t;
        hitway = TLBWay()
        hit    = Signal()
        eatag  = TLBTag()

        comb += hitway
        comb += hit
        comb += eatag

#     begin
#         tlb_req_index <=
#          to_integer(unsigned(r0.req.addr(
#           TLB_LG_PGSZ + TLB_SET_BITS - 1 downto TLB_LG_PGSZ
#          )));
#         hitway := 0;
#         hit := '0';
#         eatag := r0.req.addr(63 downto TLB_LG_PGSZ + TLB_SET_BITS);
#         for i in tlb_way_t loop
#             if tlb_valid_way(i) = '1' and
#                 read_tlb_tag(i, tlb_tag_way) = eatag then
#                 hitway := i;
#                 hit := '1';
#             end if;
#         end loop;
#         tlb_hit <= hit and r0_valid;
#         tlb_hit_way <= hitway;
        comb += tlb_req_index.eq(r0.req.addr[
                 TLB_LG_PGSZ:TLB_LG_PGSZ + TLB_SET_BITS
                ])

        comb += eatag.eq(r0.req.addr[
                 TLB_LG_PGSZ + TLB_SET_BITS:64
                ])

        for i in TLBWay():
            with m.If(tlb_valid_way(i)
                      & read_tlb_tag(i, tlb_tag_way) == eatag):

                comb += hitway.eq(i)
                comb += hit.eq(1)

        comb += tlb_hit.eq(hit & r0_valid)
        comb += tlb_hit_way.eq(hitway)

#         if tlb_hit = '1' then
        with m.If(tlb_hit):
#             pte <= read_tlb_pte(hitway, tlb_pte_way);
            comb += pte.eq(read_tlb_pte(hitway, tlb_pte_way))
#         else
        with m.Else():
#             pte <= (others => '0');
            comb += pte.eq(0)
#         end if;
#         valid_ra <= tlb_hit or not r0.req.virt_mode;
        comb += valid_ra.eq(tlb_hit | ~r0.req.virt_mode)
#         if r0.req.virt_mode = '1' then
        with m.If(r0.req.virt_mode):
#             ra <= pte(REAL_ADDR_BITS - 1 downto TLB_LG_PGSZ) &
#                   r0.req.addr(TLB_LG_PGSZ - 1 downto ROW_OFF_BITS) &
#                   (ROW_OFF_BITS-1 downto 0 => '0');
#             perm_attr <= extract_perm_attr(pte);
            comb += ra.eq(Cat(
                     Const(ROW_OFF_BITS, ROW_OFF_BITS),
                     r0.req.addr[ROW_OFF_BITS:TLB_LG_PGSZ],
                     pte[TLB_LG_PGSZ:REAL_ADDR_BITS]
                    ))
            comb += perm_attr.eq(extract_perm_attr(pte))
#         else
        with m.Else():
#             ra <= r0.req.addr(
#                    REAL_ADDR_BITS - 1 downto ROW_OFF_BITS
#                   ) & (ROW_OFF_BITS-1 downto 0 => '0');
            comb += ra.eq(Cat(
                     Const(ROW_OFF_BITS, ROW_OFF_BITS),
                     r0.rq.addr[ROW_OFF_BITS:REAL_ADDR_BITS]
                    )

#             perm_attr <= real_mode_perm_attr;
            comb += perm_attr.reference.eq(1)
            comb += perm_attr.changed.eq(1)
            comb += perm_attr.priv.eq(1)
            comb += perm_attr.nocache.eq(0)
            comb += perm_attr.rd_perm.eq(1)
            comb += perm_attr.wr_perm.eq(1)
#         end if;
#     end process;

    def tlb_update(self, r0_valid, r0, dtlb_valid_bits, tlb_req_index,
                    tlb_hit_way, tlb_hit, tlb_plru_victim, tlb_tag_way,
                    dtlb_tags, tlb_pte_way, dtlb_ptes, dtlb_valid_bits):

        comb = m.d.comb
        sync = m.d.sync

    #         variable tlbie : std_ulogic;
    #         variable tlbwe : std_ulogic;
    #         variable repl_way : tlb_way_t;
    #         variable eatag : tlb_tag_t;
    #         variable tagset : tlb_way_tags_t;
    #         variable pteset : tlb_way_ptes_t;
        tlbie    = Signal()
        tlbwe    = Signal()
        repl_way = TLBWay()
        eatag    = TLBTag()
        tagset   = TLBWayTags()
        pteset   = TLBWayPtes()

        comb += tlbie
        comb += tlbwe
        comb += repl_way
        comb += eatag
        comb += tagset
        comb += pteset

    #     begin
    #         if rising_edge(clk) then
    #             tlbie := r0_valid and r0.tlbie;
    #             tlbwe := r0_valid and r0.tlbldoi;
        sync += tlbie.eq(r0_valid & r0.tlbie)
        sync += tlbwe.eq(r0_valid & r0.tlbldoi)

    #             if rst = '1' or (tlbie = '1' and r0.doall = '1') then
    #        with m.If (TODO understand how signal resets work in nmigen)
    #                 -- clear all valid bits at once
    #                 for i in tlb_index_t loop
    #                     dtlb_valids(i) <= (others => '0');
    #                 end loop;
        # clear all valid bits at once
        for i in range(TLB_SET_SIZE):
            sync += dtlb_valid_bits[i].eq(0)

    #             elsif tlbie = '1' then
        with m.Elif(tlbie):
    #                 if tlb_hit = '1' then
            with m.If(tlb_hit):
    #                     dtlb_valids(tlb_req_index)(tlb_hit_way) <= '0';
                sync += dtlb_valid_bits[tlb_req_index][tlb_hit_way].eq(0)
    #                 end if;
    #             elsif tlbwe = '1' then
        with m.Elif(tlbwe):
    #                 if tlb_hit = '1' then
            with m.If(tlb_hit):
    #                     repl_way := tlb_hit_way;
                sync += repl_way.eq(tlb_hit_way)
    #                 else
            with m.Else():
    #                     repl_way := to_integer(unsigned(
    #                       tlb_plru_victim(tlb_req_index)));
                sync += repl_way.eq(tlb_plru_victim[tlb_req_index])
    #                 end if;
    #                 eatag := r0.req.addr(
    #                           63 downto TLB_LG_PGSZ + TLB_SET_BITS
    #                          );
    #                 tagset := tlb_tag_way;
    #                 write_tlb_tag(repl_way, tagset, eatag);
    #                 dtlb_tags(tlb_req_index) <= tagset;
    #                 pteset := tlb_pte_way;
    #                 write_tlb_pte(repl_way, pteset, r0.req.data);
    #                 dtlb_ptes(tlb_req_index) <= pteset;
    #                 dtlb_valids(tlb_req_index)(repl_way) <= '1';
            sync += eatag.eq(r0.req.addr[TLB_LG_PGSZ + TLB_SET_BITS:64])
            sync += tagset.eq(tlb_tag_way)
            sync += write_tlb_tag(repl_way, tagset, eatag)
            sync += dtlb_tags[tlb_req_index].eq(tagset)
            sync += pteset.eq(tlb_pte_way)
            sync += write_tlb_pte(repl_way, pteset, r0.req.data)
            sync += dtlb_ptes[tlb_req_index].eq(pteset)
            sync += dtlb_valid_bits[tlb_req_index][repl_way].eq(1)
    #             end if;
    #         end if;
    #     end process;

#     -- Generate PLRUs
#     maybe_plrus: if NUM_WAYS > 1 generate
    # Generate PLRUs
    def maybe_plrus(self, r1):

        comb = m.d.comb
        sync = m.d.sync

#     begin
        # TODO learn translation of generate into nmgien @lkcl
# 	plrus: for i in 0 to NUM_LINES-1 generate
        for i in range(NUM_LINES):
# 	    -- PLRU interface
# 	    signal plru_acc    : std_ulogic_vector(WAY_BITS-1 downto 0);
# 	    signal plru_acc_en : std_ulogic;
# 	    signal plru_out    : std_ulogic_vector(WAY_BITS-1 downto 0);
            plru        = PLRU(WAY_BITS)
            plru_acc    = Signal(WAY_BITS)
            plru_acc_en = Signal()
            plru_out    = Signal(WAY_BITS)
#
# 	begin
        # TODO learn tranlation of entity, generic map, port map in
        # nmigen @lkcl
# 	    plru : entity work.plru
# 		generic map (
# 		    BITS => WAY_BITS
# 		    )
# 		port map (
# 		    clk => clk,
# 		    rst => rst,
# 		    acc => plru_acc,
# 		    acc_en => plru_acc_en,
# 		    lru => plru_out
# 		    );
            comb += plru.acc.eq(plru_acc)
            comb += plru.acc_en.eq(plru_acc_en)
            comb += plru.lru.eq(plru_out)

# 	    process(all)
# 	    begin
# 		-- PLRU interface
# 		if r1.hit_index = i then
            # PLRU interface
            with m.If(r1.hit_index == i):
# 		    plru_acc_en <= r1.cache_hit;
                comb += plru_acc_en.eq(r1.cache_hit)
# 		else
            with m.Else():
# 	    	    plru_acc_en <= '0';
                comb += plru_acc_en.eq(0)
# 		end if;
# 		plru_acc <= std_ulogic_vector(to_unsigned(
#                            r1.hit_way, WAY_BITS
#                           ));
# 		plru_victim(i) <= plru_out;
            comb += plru_acc.eq(r1.hit_way)
            comb += plru_victim[i].eq(plru_out)
# 	    end process;
# 	end generate;
#     end generate;

#     -- Cache tag RAM read port
#     cache_tag_read : process(clk)
    # Cache tag RAM read port
    def cache_tag_read(self, r0_stall, req_index, m_in, d_in,
                       cache_tag_set, cache_tags):

        comb = m.d.comb
        sync = m.d.sync

#         variable index : index_t;
        index = Signal(NUM_LINES)

        comb += index

#     begin
#         if rising_edge(clk) then
#             if r0_stall = '1' then
        with m.If(r0_stall):
#                 index := req_index;
            sync += index.eq(req_index)

#             elsif m_in.valid = '1' then
        with m.Elif(m_in.valid):
#                 index := get_index(m_in.addr);
            sync += index.eq(get_index(m_in.addr))

#             else
        with m.Else():
#                 index := get_index(d_in.addr);
            sync += index.eq(get_index(d_in.addr))
#             end if;
#             cache_tag_set <= cache_tags(index);
        sync += cache_tag_set.eq(cache_tags[index])
#         end if;
#     end process;

    # Cache request parsing and hit detection
    def dcache_request(self, r0, ra, req_index, req_row, req_tag,
                       r0_valid, r1, cache_valid_bits, replace_way,
                       use_forward1_next, use_forward2_next,
                       req_hit_way, plru_victim, rc_ok, perm_attr,
                       valid_ra, perm_ok, access_ok, req_op, req_ok,
                       r0_stall, m_in, early_req_row, d_in):

        comb = m.d.comb
        sync = m.d.sync

#         variable is_hit  : std_ulogic;
#         variable hit_way : way_t;
#         variable op      : op_t;
#         variable opsel   : std_ulogic_vector(2 downto 0);
#         variable go      : std_ulogic;
#         variable nc      : std_ulogic;
#         variable s_hit   : std_ulogic;
#         variable s_tag   : cache_tag_t;
#         variable s_pte   : tlb_pte_t;
#         variable s_ra    : std_ulogic_vector(
#                             REAL_ADDR_BITS - 1 downto 0
#                            );
#         variable hit_set     : std_ulogic_vector(
#                                 TLB_NUM_WAYS - 1 downto 0
#                                );
#         variable hit_way_set : hit_way_set_t;
#         variable rel_matches : std_ulogic_vector(
#                                 TLB_NUM_WAYS - 1 downto 0
#                                );
        rel_match   = Signal()
        is_hit      = Signal()
        hit_way     = Signal(WAY_BITS)
        op          = Op()
        opsel       = Signal(3)
        go          = Signal()
        nc          = Signal()
        s_hit       = Signal()
        s_tag       = Signal(TAG_BITS)
        s_pte       = Signal(TLB_PTE_BITS)
        s_ra        = Signal(REAL_ADDR_BITS)
        hit_set     = Signal(TLB_NUM_WAYS)
        hit_way_set = HitWaySet()
        rel_matches = Signal(TLB_NUM_WAYS)
        rel_match   = Signal()

#     begin
# 	  -- Extract line, row and tag from request
#         req_index <= get_index(r0.req.addr);
#         req_row <= get_row(r0.req.addr);
#         req_tag <= get_tag(ra);
#
#         go := r0_valid and not (r0.tlbie or r0.tlbld)
#               and not r1.ls_error;
        # Extract line, row and tag from request
        comb += req_index.eq(get_index(r0.req.addr))
        comb += req_row.eq(get_row(r0.req.addr))
        comb += req_tag.eq(get_tag(ra))

        comb += go.eq(r0_valid & ~(r0.tlbie | r0.tlbld) & ~r1.ls_error)

#         hit_way := 0;
#         is_hit := '0';
#         rel_match := '0';
        # Test if pending request is a hit on any way
        # In order to make timing in virtual mode,
        # when we are using the TLB, we compare each
        # way with each of the real addresses from each way of
        # the TLB, and then decide later which match to use.

#         if r0.req.virt_mode = '1' then
        with m.If(r0.req.virt_mode):
#             rel_matches := (others => '0');
            comb += rel_matches.eq(0)
#             for j in tlb_way_t loop
            for j in range(TLB_NUM_WAYS):
#                 hit_way_set(j) := 0;
#                 s_hit := '0';
#                 s_pte := read_tlb_pte(j, tlb_pte_way);
#                 s_ra  := s_pte(REAL_ADDR_BITS - 1 downto TLB_LG_PGSZ)
#                          & r0.req.addr(TLB_LG_PGSZ - 1 downto 0);
#                 s_tag := get_tag(s_ra);
                comb += hit_way_set[j].eq(0)
                comb += s_hit.eq(0)
                comb += s_pte.eq(read_tlb_pte(j, tlb_pte_way))
                comb += s_ra.eq(Cat(
                         r0.req.addr[0:TLB_LG_PGSZ],
                         s_pte[TLB_LG_PGSZ:REAL_ADDR_BITS]
                        ))
                comb += s_tag.eq(get_tag(s_ra))

#                 for i in way_t loop
                for i in range(NUM_WAYS):
#                     if go = '1' and cache_valids(req_index)(i) = '1'
#                      and read_tag(i, cache_tag_set) = s_tag
#                      and tlb_valid_way(j) = '1' then
                    with m.If(go & cache_valid_bits[req_index][i] &
                              read_tag(i, cache_tag_set) == s_tag
                              & tlb_valid_way[j]):
#                         hit_way_set(j) := i;
#                         s_hit := '1';
                        comb += hit_way_set[j].eq(i)
                        comb += s_hit.eq(1)
#                     end if;
#                 end loop;
#                 hit_set(j) := s_hit;
                comb += hit_set[j].eq(s_hit)
#                 if s_tag = r1.reload_tag then
                with m.If(s_tag == r1.reload_tag):
#                     rel_matches(j) := '1';
                    comb += rel_matches[j].eq(1)
#                 end if;
#             end loop;
#             if tlb_hit = '1' then
            with m.If(tlb_hit):
#                 is_hit := hit_set(tlb_hit_way);
#                 hit_way := hit_way_set(tlb_hit_way);
#                 rel_match := rel_matches(tlb_hit_way);
                comb += is_hit.eq(hit_set[tlb_hit_way])
                comb += hit_way.eq(hit_way_set[tlb_hit_way])
                comb += rel_match.eq(rel_matches[tlb_hit_way])
#             end if;
#         else
        with m.Else():
#             s_tag := get_tag(r0.req.addr);
            comb += s_tag.eq(get_tag(r0.req.addr))
#             for i in way_t loop
            for i in range(NUM_WAYS):
#                 if go = '1' and cache_valids(req_index)(i) = '1' and
#                     read_tag(i, cache_tag_set) = s_tag then
                with m.If(go & cache_valid_bits[req_index][i] &
                          read_tag(i, cache_tag_set) == s_tag):
#                     hit_way := i;
#                     is_hit := '1';
                    comb += hit_way.eq(i)
                    comb += is_hit.eq(1)
#                 end if;
#             end loop;
#             if s_tag = r1.reload_tag then
            with m.If(s_tag == r1.reload_tag):
#                 rel_match := '1';
                comb += rel_match.eq(1)
#             end if;
#         end if;
#         req_same_tag <= rel_match;
        comb += req_same_tag.eq(rel_match)

#         if r1.state = RELOAD_WAIT_ACK and req_index = r1.store_index
#          and rel_match = '1' then
        # See if the request matches the line currently being reloaded
        with m.If(r1.state == State.RELOAD_WAIT_ACK & req_index ==
                  r1.store_index & rel_match):
            # For a store, consider this a hit even if the row isn't
            # valid since it will be by the time we perform the store.
            # For a load, check the appropriate row valid bit.
#             is_hit :=
#              not r0.req.load
#               or r1.rows_valid(req_row mod ROW_PER_LINE);
#             hit_way := replace_way;
            comb += is_hit.eq(~r0.req.load
                              | r1.rows_valid[req_row % ROW_PER_LINE]
                             )
            comb += hit_way.eq(replace_way)
#         end if;

#         -- Whether to use forwarded data for a load or not
        # Whether to use forwarded data for a load or not
#         use_forward1_next <= '0';
        comb += use_forward1_next.eq(0)
#         if get_row(r1.req.real_addr) = req_row
#          and r1.req.hit_way = hit_way then
        with m.If(get_row(r1.req.real_addr) == req_row
                  & r1.req.hit_way == hit_way)
            # Only need to consider r1.write_bram here, since if we
            # are writing refill data here, then we don't have a
            # cache hit this cycle on the line being refilled.
            # (There is the possibility that the load following the
            # load miss that started the refill could be to the old
            # contents of the victim line, since it is a couple of
            # cycles after the refill starts before we see the updated
            # cache tag. In that case we don't use the bypass.)
#             use_forward1_next <= r1.write_bram;
            comb += use_forward1_next.eq(r1.write_bram)
#         end if;
#         use_forward2_next <= '0';
        comb += use_forward2_next.eq(0)
#         if r1.forward_row1 = req_row
#          and r1.forward_way1 = hit_way then
        with m.If(r1.forward_row1 == req_row
                  & r1.forward_way1 == hit_way):
#             use_forward2_next <= r1.forward_valid1;
            comb += use_forward2_next.eq(r1.forward_valid1)
#         end if;

        # The way that matched on a hit
# 	    req_hit_way <= hit_way;
        comb += req_hit_way.eq(hit_way)

        # The way to replace on a miss
#         if r1.write_tag = '1' then
        with m.If(r1.write_tag):
#             replace_way <= to_integer(unsigned(
#                             plru_victim(r1.store_index)
#                            ));
            replace_way.eq(plru_victim[r1.store_index])
#         else
        with m.Else():
#             replace_way <= r1.store_way;
            comb += replace_way.eq(r1.store_way)
#         end if;

        # work out whether we have permission for this access
        # NB we don't yet implement AMR, thus no KUAP
#         rc_ok <= perm_attr.reference and
#                  (r0.req.load or perm_attr.changed);
#         perm_ok <= (r0.req.priv_mode or not perm_attr.priv) and
#                    (perm_attr.wr_perm or (r0.req.load
#                    and perm_attr.rd_perm));
#         access_ok <= valid_ra and perm_ok and rc_ok;
        comb += rc_ok.eq(
                 perm_attr.reference
                 & (r0.req.load | perm_attr.changed)
                )
        comb += perm_ok.eq((r0.req.prive_mode | ~perm_attr.priv)
                           & perm_attr.wr_perm
                           | (r0.req.load & perm_attr.rd_perm)
                          )
        comb += access_ok.eq(valid_ra & perm_ok & rc_ok)
#         nc := r0.req.nc or perm_attr.nocache;
#         op := OP_NONE;
        # Combine the request and cache hit status to decide what
        # operation needs to be done
        comb += nc.eq(r0.req.nc | perm_attr.nocache)
        comb += op.eq(Op.OP_NONE)
#         if go = '1' then
        with m.If(go):
#             if access_ok = '0' then
            with m.If(~access_ok):
#                 op := OP_BAD;
                comb += op.eq(Op.OP_BAD)
#             elsif cancel_store = '1' then
            with m.Elif(cancel_store):
#                 op := OP_STCX_FAIL;
                comb += op.eq(Op.OP_STCX_FAIL)
#             else
            with m.Else():
#                 opsel := r0.req.load & nc & is_hit;
                comb += opsel.eq(Cat(is_hit, nc, r0.req.load))
#                 case opsel is
                with m.Switch(opsel):
#                     when "101" => op := OP_LOAD_HIT;
#                     when "100" => op := OP_LOAD_MISS;
#                     when "110" => op := OP_LOAD_NC;
#                     when "001" => op := OP_STORE_HIT;
#                     when "000" => op := OP_STORE_MISS;
#                     when "010" => op := OP_STORE_MISS;
#                     when "011" => op := OP_BAD;
#                     when "111" => op := OP_BAD;
#                     when others => op := OP_NONE;
                    with m.Case(Const(0b101, 3)):
                        comb += op.eq(Op.OP_LOAD_HIT)

                    with m.Case(Cosnt(0b100, 3)):
                        comb += op.eq(Op.OP_LOAD_MISS)

                    with m.Case(Const(0b110, 3)):
                        comb += op.eq(Op.OP_LOAD_NC)

                    with m.Case(Const(0b001, 3)):
                        comb += op.eq(Op.OP_STORE_HIT)

                    with m.Case(Const(0b000, 3)):
                        comb += op.eq(Op.OP_STORE_MISS)

                    with m.Case(Const(0b010, 3)):
                        comb += op.eq(Op.OP_STORE_MISS)

                    with m.Case(Const(0b011, 3)):
                        comb += op.eq(Op.OP_BAD)

                    with m.Case(Const(0b111, 3)):
                        comb += op.eq(Op.OP_BAD)

                    with m.Default():
                        comb += op.eq(Op.OP_NONE)
#                 end case;
#             end if;
#         end if;
# 	req_op <= op;
#         req_go <= go;
        comb += req_op.eq(op)
        comb += req_go.eq(go)

        # Version of the row number that is valid one cycle earlier
        # in the cases where we need to read the cache data BRAM.
        # If we're stalling then we need to keep reading the last
        # row requested.
#         if r0_stall = '0' then
        with m.If(~r0_stall):
#             if m_in.valid = '1' then
            with m.If(m_in.valid):
#                 early_req_row <= get_row(m_in.addr);
                comb += early_req_row.eq(get_row(m_in.addr))
#             else
            with m.Else():
#                 early_req_row <= get_row(d_in.addr);
                comb += early_req_row.eq(get_row(d_in.addr))
#             end if;
#         else
        with m.Else():
#             early_req_row <= req_row;
            comb += early_req_row.eq(req_row)
#         end if;
#     end process;

    # Handle load-with-reservation and store-conditional instructions
    def reservation_comb(self, cancel_store, set_rsrv, clear_rsrv,
                         r0_valid, r0, reservation):

        comb = m.d.comb
        sync = m.d.sync

#     begin
#         cancel_store <= '0';
#         set_rsrv <= '0';
#         clear_rsrv <= '0';
#         if r0_valid = '1' and r0.req.reserve = '1' then
        with m.If(r0_valid & r0.req.reserve):

#             -- XXX generate alignment interrupt if address
#             -- is not aligned XXX or if r0.req.nc = '1'
#             if r0.req.load = '1' then
            # XXX generate alignment interrupt if address
            # is not aligned XXX or if r0.req.nc = '1'
            with m.If(r0.req.load):
#                 -- load with reservation
#                 set_rsrv <= '1';
                # load with reservation
                comb += set_rsrv(1)
#             else
            with m.Else():
#                 -- store conditional
#                 clear_rsrv <= '1';
                # store conditional
                comb += clear_rsrv.eq(1)
#                 if reservation.valid = '0' or r0.req.addr(63
#                  downto LINE_OFF_BITS) /= reservation.addr then
                with m.If(~reservation.valid
                          | r0.req.addr[LINE_OFF_BITS:64]):
#                     cancel_store <= '1';
                    comb += cancel_store.eq(1)
#                 end if;
#             end if;
#         end if;
#     end process;

    def reservation_reg(self, r0_valid, access_ok, clear_rsrv,
                        reservation, r0):

        comb = m.d.comb
        sync = m.d.sync

#     begin
#         if rising_edge(clk) then
#             if rst = '1' then
#                 reservation.valid <= '0';
            # TODO understand how resets work in nmigen
#             elsif r0_valid = '1' and access_ok = '1' then
            with m.Elif(r0_valid & access_ok):
#                 if clear_rsrv = '1' then
                with m.If(clear_rsrv):
#                     reservation.valid <= '0';
                    sync += reservation.valid.ea(0)
#                 elsif set_rsrv = '1' then
                with m.Elif(set_rsrv):
#                     reservation.valid <= '1';
#                     reservation.addr <=
#                      r0.req.addr(63 downto LINE_OFF_BITS);
                    sync += reservation.valid.eq(1)
                    sync += reservation.addr.eq(
                             r0.req.addr[LINE_OFF_BITS:64]
                            )
#                 end if;
#             end if;
#         end if;
#     end process;

    # Return data for loads & completion control logic
    def writeback_control(self, r1, cache_out, d_out, m_out):

        comb = m.d.comb
        sync = m.d.sync

#         variable data_out : std_ulogic_vector(63 downto 0);
#         variable data_fwd : std_ulogic_vector(63 downto 0);
#         variable j        : integer;
        data_out = Signal(64)
        data_fwd = Signal(64)
        j        = Signal()

#     begin
#         -- Use the bypass if are reading the row that was
#         -- written 1 or 2 cycles ago, including for the
#         -- slow_valid = 1 case (i.e. completing a load
#         -- miss or a non-cacheable load).
#         if r1.use_forward1 = '1' then
        # Use the bypass if are reading the row that was
        # written 1 or 2 cycles ago, including for the
        # slow_valid = 1 case (i.e. completing a load
        # miss or a non-cacheable load).
        with m.If(r1.use_forward1):
#             data_fwd := r1.forward_data1;
            comb += data_fwd.eq(r1.forward_data1)
#         else
        with m.Else():
#             data_fwd := r1.forward_data2;
            comb += data_fwd.eq(r1.forward_data2)
#         end if;

#         data_out := cache_out(r1.hit_way);
        comb += data_out.eq(cache_out[r1.hit_way])

#         for i in 0 to 7 loop
        for i in range(8):
#             j := i * 8;
            comb += i * 8

#             if r1.forward_sel(i) = '1' then
            with m.If(r1.forward_sel[i]):
#                 data_out(j + 7 downto j) := data_fwd(j + 7 downto j);
                comb += data_out[j:j+8].eq(data_fwd[j:j+8])
#             end if;
#         end loop;

# 	  d_out.valid <= r1.ls_valid;
# 	  d_out.data <= data_out;
#         d_out.store_done <= not r1.stcx_fail;
#         d_out.error <= r1.ls_error;
#         d_out.cache_paradox <= r1.cache_paradox;
        comb += d_out.valid.eq(r1.ls_valid)
        comb += d_out.data.eq(data_out)
        comb += d_out.store_done.eq(~r1.stcx_fail)
        comb += d_out.error.eq(r1.ls_error)
        comb += d_out.cache_paradox.eq(r1.cache_paradox)

#         -- Outputs to MMU
#         m_out.done <= r1.mmu_done;
#         m_out.err <= r1.mmu_error;
#         m_out.data <= data_out;
        comb += m_out.done.eq(r1.mmu_done)
        comb += m_out.err.eq(r1.mmu_error)
        comb += m_out.data.eq(data_out)

# 	  -- We have a valid load or store hit or we just completed
#         -- a slow op such as a load miss, a NC load or a store
# 	  --
# 	  -- Note: the load hit is delayed by one cycle. However it
#         -- can still not collide with r.slow_valid (well unless I
#         -- miscalculated) because slow_valid can only be set on a
#         -- subsequent request and not on its first cycle (the state
#         -- machine must have advanced), which makes slow_valid
#         -- at least 2 cycles from the previous hit_load_valid.
#
# 	  -- Sanity: Only one of these must be set in any given cycle
# 	  assert (r1.slow_valid and r1.stcx_fail) /= '1'
#          report "unexpected slow_valid collision with stcx_fail"
# 	   severity FAILURE;
# 	  assert ((r1.slow_valid or r1.stcx_fail) and r1.hit_load_valid)
#          /= '1' report "unexpected hit_load_delayed collision with
#          slow_valid" severity FAILURE;
        # We have a valid load or store hit or we just completed
        # a slow op such as a load miss, a NC load or a store
        #
        # Note: the load hit is delayed by one cycle. However it
        # can still not collide with r.slow_valid (well unless I
        # miscalculated) because slow_valid can only be set on a
        # subsequent request and not on its first cycle (the state
        # machine must have advanced), which makes slow_valid
        # at least 2 cycles from the previous hit_load_valid.

        # Sanity: Only one of these must be set in any given cycle
        assert (r1.slow_valid & r1.stcx_fail) != 1 "unexpected" \
         "slow_valid collision with stcx_fail -!- severity FAILURE"

        assert ((r1.slow_valid | r1.stcx_fail) | r1.hit_load_valid) != 1
         "unexpected hit_load_delayed collision with slow_valid -!-" \
         "severity FAILURE"

#         if r1.mmu_req = '0' then
        with m.If(~r1._mmu_req):
#             -- Request came from loadstore1...
#             -- Load hit case is the standard path
#             if r1.hit_load_valid = '1' then
            # Request came from loadstore1...
            # Load hit case is the standard path
            with m.If(r1.hit_load_valid):
#                 report
#                  "completing load hit data=" & to_hstring(data_out);
                print(f"completing load hit data={data_out}")
#             end if;

#             -- error cases complete without stalling
#             if r1.ls_error = '1' then
            # error cases complete without stalling
            with m.If(r1.ls_error):
#                 report "completing ld/st with error";
                print("completing ld/st with error")
#             end if;

#             -- Slow ops (load miss, NC, stores)
#             if r1.slow_valid = '1' then
            # Slow ops (load miss, NC, stores)
            with m.If(r1.slow_valid):
#                 report
#                  "completing store or load miss data="
#                   & to_hstring(data_out);
                print(f"completing store or load miss data={data_out}")
#             end if;

#         else
        with m.Else():
#             -- Request came from MMU
#             if r1.hit_load_valid = '1' then
            # Request came from MMU
            with m.If(r1.hit_load_valid):
#                 report "completing load hit to MMU, data="
#                  & to_hstring(m_out.data);
                print(f"completing load hit to MMU, data={m_out.data}")
#             end if;
#
#             -- error cases complete without stalling
#             if r1.mmu_error = '1' then
#                 report "completing MMU ld with error";
            # error cases complete without stalling
            with m.If(r1.mmu_error):
                print("combpleting MMU ld with error")
#             end if;
#
#             -- Slow ops (i.e. load miss)
#             if r1.slow_valid = '1' then
            # Slow ops (i.e. load miss)
            with m.If(r1.slow_valid):
#                 report "completing MMU load miss, data="
#                  & to_hstring(m_out.data);
                print("completing MMU load miss, data={m_out.data}")
#             end if;
#         end if;
#     end process;

#     -- Generate a cache RAM for each way. This handles the normal
#     -- reads, writes from reloads and the special store-hit update
#     -- path as well.
#     --
#     -- Note: the BRAMs have an extra read buffer, meaning the output
#     -- is pipelined an extra cycle. This differs from the
#     -- icache. The writeback logic needs to take that into
#     -- account by using 1-cycle delayed signals for load hits.
#     --
#     rams: for i in 0 to NUM_WAYS-1 generate
    # Generate a cache RAM for each way. This handles the normal
    # reads, writes from reloads and the special store-hit update
    # path as well.
    #
    # Note: the BRAMs have an extra read buffer, meaning the output
    # is pipelined an extra cycle. This differs from the
    # icache. The writeback logic needs to take that into
    # account by using 1-cycle delayed signals for load hits.
    def rams(self, ):
        for i in range(NUM_WAYS):
# 	signal do_read  : std_ulogic;
# 	signal rd_addr  : std_ulogic_vector(ROW_BITS-1 downto 0);
# 	signal do_write : std_ulogic;
# 	signal wr_addr  : std_ulogic_vector(ROW_BITS-1 downto 0);
# 	signal wr_data  :
#        std_ulogic_vector(wishbone_data_bits-1 downto 0);
# 	signal wr_sel   : std_ulogic_vector(ROW_SIZE-1 downto 0);
# 	signal wr_sel_m : std_ulogic_vector(ROW_SIZE-1 downto 0);
# 	signal dout     : cache_row_t;
            do_read  = Signal()
            rd_addr  = Signal(ROW_BITS)
            do_write = Signal()
            wr_addr  = Signal(ROW_BITS)
            wr_data  = Signal(WB_DATA_BITS)
            wr_sel   = Signal(ROW_SIZE)
            wr_sel_m = Signal(ROW_SIZE)
            _d_out   = Signal(WB_DATA_BITS)

#     begin
# 	way: entity work.cache_ram
# 	    generic map (
# 		ROW_BITS => ROW_BITS,
# 		WIDTH => wishbone_data_bits,
# 		ADD_BUF => true
# 		)
# 	    port map (
# 		clk     => clk,
# 		rd_en   => do_read,
# 		rd_addr => rd_addr,
# 		rd_data => dout,
# 		wr_sel  => wr_sel_m,
# 		wr_addr => wr_addr,
# 		wr_data => wr_data
# 		);
# 	process(all)
            way = CacheRam(ROW_BITS, WB_DATA_BITS, True)
            comb += way.rd_en.eq(do_read)
            comb += way.rd_addr.eq(rd_addr)
            comb += way.rd_data.eq(_d_out)
            comb += way.wr_sel.eq(wr_sel_m)
            comb += way.wr_addr.eq(wr_addr)
            comb += way.wr_data.eq(wr_data)

# 	begin
# 	    -- Cache hit reads
# 	    do_read <= '1';
# 	    rd_addr <=
#            std_ulogic_vector(to_unsigned(early_req_row, ROW_BITS));
# 	    cache_out(i) <= dout;
            # Cache hit reads
            comb += do_read.eq(1)
            comb += rd_addr.eq(Signal(BRAM_ROWS))
            comb += cache_out[i].eq(dout)

# 	    -- Write mux:
# 	    --
# 	    -- Defaults to wishbone read responses (cache refill)
# 	    --
# 	    -- For timing, the mux on wr_data/sel/addr is not
#           -- dependent on anything other than the current state.
        # Write mux:
        #
        # Defaults to wishbone read responses (cache refill)
        #
        # For timing, the mux on wr_data/sel/addr is not
        # dependent on anything other than the current state.
#           wr_sel_m <= (others => '0');
            comb += wr_sel_m.eq(0)

# 	    do_write <= '0';
            comb += do_write.eq(0)
#             if r1.write_bram = '1' then
            with m.If(r1.write_bram):
#                 -- Write store data to BRAM.  This happens one
#                 -- cycle after the store is in r0.
                # Write store data to BRAM.  This happens one
                # cycle after the store is in r0.
#                 wr_data <= r1.req.data;
#                 wr_sel  <= r1.req.byte_sel;
#                 wr_addr <= std_ulogic_vector(to_unsigned(
#                             get_row(r1.req.real_addr), ROW_BITS
#                            ));
                comb += wr_data.eq(r1.req.data)
                comb += wr_sel.eq(r1.req.byte_sel)
                comb += wr_addr.eq(Signal(get_row(r1.req.real_addr)))

#                 if i = r1.req.hit_way then
                with m.If(i == r1.req.hit_way):
#                     do_write <= '1';
                    comb += do_write.eq(1)
#                 end if;
# 	    else
                with m.Else():
# 		-- Otherwise, we might be doing a reload or a DCBZ
#                 if r1.dcbz = '1' then
                # Otherwise, we might be doing a reload or a DCBZ
                    with m.If(r1.dcbz):
#                     wr_data <= (others => '0');
                        comb += wr_data.eq(0)
#                 else
                    with m.Else():
#                     wr_data <= wishbone_in.dat;
                        comb += wr_data.eq(wishbone_in.dat)
#                 end if;

#                 wr_addr <= std_ulogic_vector(to_unsigned(
#                             r1.store_row, ROW_BITS
#                            ));
#                 wr_sel <= (others => '1');
                    comb += wr_addr.eq(Signal(r1.store_row))
                    comb += wr_sel.eq(1)

#                 if r1.state = RELOAD_WAIT_ACK and
#                 wishbone_in.ack = '1' and replace_way = i then
                with m.If(r1.state == State.RELOAD_WAIT_ACK
                          & wishbone_in.ack & relpace_way == i):
#                     do_write <= '1';
                    comb += do_write.eq(1)
#                 end if;
# 	    end if;

#             -- Mask write selects with do_write since BRAM
#             -- doesn't have a global write-enable
#             if do_write = '1' then
#             -- Mask write selects with do_write since BRAM
#             -- doesn't have a global write-enable
                with m.If(do_write):
#                 wr_sel_m <= wr_sel;
                    comb += wr_sel_m.eq(wr_sel)
#             end if;
#         end process;
#     end generate;

    # Cache hit synchronous machine for the easy case.
    # This handles load hits.
    # It also handles error cases (TLB miss, cache paradox)
    def dcache_fast_hit(self, req_op, r0_valid, r1, ):

        comb = m.d.comb
        sync = m.d.sync

#     begin
#         if rising_edge(clk) then
#             if req_op /= OP_NONE then
        with m.If(req_op != Op.OP_NONE):
# 		report "op:" & op_t'image(req_op) &
# 		    " addr:" & to_hstring(r0.req.addr) &
# 		    " nc:" & std_ulogic'image(r0.req.nc) &
# 		    " idx:" & integer'image(req_index) &
# 		    " tag:" & to_hstring(req_tag) &
# 		    " way: " & integer'image(req_hit_way);
            print(f"op:{req_op} addr:{r0.req.addr} nc: {r0.req.nc}" \
                  f"idx:{req_index} tag:{req_tag} way: {req_hit_way}"
                 )
# 	      end if;
#             if r0_valid = '1' then
        with m.If(r0_valid):
#                 r1.mmu_req <= r0.mmu_req;
            sync += r1.mmu_req.eq(r0.mmu_req)
#             end if;

#             -- Fast path for load/store hits.
#             -- Set signals for the writeback controls.
#             r1.hit_way <= req_hit_way;
#             r1.hit_index <= req_index;
        # Fast path for load/store hits.
        # Set signals for the writeback controls.
        sync += r1.hit_way.eq(req_hit_way)
        sync += r1.hit_index.eq(req_index)

# 	      if req_op = OP_LOAD_HIT then
        with m.If(req_op == Op.OP_LOAD_HIT):
# 	          r1.hit_load_valid <= '1';
            sync += r1.hit_load_valid.eq(1)

# 	      else
        with m.Else():
# 		  r1.hit_load_valid <= '0';
            sync += r1.hit_load_valid.eq(0)
# 	      end if;

#             if req_op = OP_LOAD_HIT or req_op = OP_STORE_HIT then
        with m.If(req_op == Op.OP_LOAD_HIT | req_op == Op.OP_STORE_HIT):
#                 r1.cache_hit <= '1';
            sync += r1.cache_hit.eq(1)
#             else
        with m.Else():
#                 r1.cache_hit <= '0';
            sync += r1.cache_hit.eq(0)
#             end if;

#             if req_op = OP_BAD then
        with m.If(req_op == Op.OP_BAD):
#                 report "Signalling ld/st error valid_ra=" &
#                  std_ulogic'image(valid_ra) & " rc_ok=" &
#                  std_ulogic'image(rc_ok) & " perm_ok=" &
#                  std_ulogic'image(perm_ok);
            print(f"Signalling ld/st error valid_ra={valid_ra}"
                  f"rc_ok={rc_ok} perm_ok={perm_ok}"

#                 r1.ls_error <= not r0.mmu_req;
#                 r1.mmu_error <= r0.mmu_req;
#                 r1.cache_paradox <= access_ok;
            sync += r1.ls_error.eq(~r0.mmu_req)
            sync += r1.mmu_error.eq(r0.mmu_req)
            sync += r1.cache_paradox.eq(access_ok)

#             else
            with m.Else():
#                 r1.ls_error <= '0';
#                 r1.mmu_error <= '0';
#                 r1.cache_paradox <= '0';
                sync += r1.ls_error.eq(0)
                sync += r1.mmu_error.eq(0)
                sync += r1.cache_paradox.eq(0)
#             end if;
#
#             if req_op = OP_STCX_FAIL then
            with m.If(req_op == Op.OP_STCX_FAIL):
#                 r1.stcx_fail <= '1';
                r1.stcx_fail.eq(1)

#             else
            with m.Else():
#                 r1.stcx_fail <= '0';
                sync += r1.stcx_fail.eq(0)
#             end if;
#
#             -- Record TLB hit information for updating TLB PLRU
#             r1.tlb_hit <= tlb_hit;
#             r1.tlb_hit_way <= tlb_hit_way;
#             r1.tlb_hit_index <= tlb_req_index;
            # Record TLB hit information for updating TLB PLRU
            sync += r1.tlb_hit.eq(tlb_hit)
            sync += r1.tlb_hit_way.eq(tlb_hit_way)
            sync += r1.tlb_hit_index.eq(tlb_req_index)
# 	  end if;
#     end process;

    # Memory accesses are handled by this state machine:
    #
    #   * Cache load miss/reload (in conjunction with "rams")
    #   * Load hits for non-cachable forms
    #   * Stores (the collision case is handled in "rams")
    #
    # All wishbone requests generation is done here.
    # This machine operates at stage 1.
    def dcache_slow(self, r1, use_forward1_next, cache_valid_bits, r0,
                    r0_valid, req_op, cache_tag, req_go, ra, wb_in):

        comb = m.d.comb
        sync = m.d.sync

# 	  variable stbs_done : boolean;
#         variable req       : mem_access_request_t;
#         variable acks      : unsigned(2 downto 0);
        stbs_done = Signal()
        req       = MemAccessRequest()
        acks      = Signal(3)

        comb += stbs_done
        comb += req
        comb += acks

#     begin
#         if rising_edge(clk) then
#             r1.use_forward1 <= use_forward1_next;
#             r1.forward_sel <= (others => '0');
        sync += r1.use_forward1.eq(use_forward1_next)
        sync += r1.forward_sel.eq(0)

#             if use_forward1_next = '1' then
        with m.If(use_forward1_next):
#                 r1.forward_sel <= r1.req.byte_sel;
            sync += r1.forward_sel.eq(r1.req.byte_sel)

#           elsif use_forward2_next = '1' then
        with m.Elif(use_forward2_next):
#                 r1.forward_sel <= r1.forward_sel1;
            sync += r1.forward_sel.eq(r1.forward_sel1)
#             end if;

#             r1.forward_data2 <= r1.forward_data1;
        sync += r1.forward_data2.eq(r1.forward_data1)

#             if r1.write_bram = '1' then
        with m.If(r1.write_bram):
#                 r1.forward_data1 <= r1.req.data;
#                 r1.forward_sel1 <= r1.req.byte_sel;
#                 r1.forward_way1 <= r1.req.hit_way;
#                 r1.forward_row1 <= get_row(r1.req.real_addr);
#                 r1.forward_valid1 <= '1';
            sync += r1.forward_data1.eq(r1.req.data)
            sync += r1.forward_sel1.eq(r1.req.byte_sel)
            sync += r1.forward_way1.eq(r1.req.hit_way)
            sync += r1.forward_row1.eq(get_row(r1.req.real_addr))
            sync += r1.forward_valid1.eq(1)
#             else
        with m.Else():

#                 if r1.dcbz = '1' then
            with m.If(r1.bcbz):
#                     r1.forward_data1 <= (others => '0');
                sync += r1.forward_data1.eq(0)

#                 else
            with m.Else():
#                     r1.forward_data1 <= wishbone_in.dat;
                sync += r1.forward_data1.eq(wb_in.dat)
#                 end if;

#                 r1.forward_sel1 <= (others => '1');
#                 r1.forward_way1 <= replace_way;
#                 r1.forward_row1 <= r1.store_row;
#                 r1.forward_valid1 <= '0';
            sync += r1.forward_sel1.eq(1)
            sync += r1.forward_way1.eq(replace_way)
            sync += r1.forward_row1.eq(r1.store_row)
            sync += r1.forward_valid1.eq(0)
#             end if;

# 	    -- On reset, clear all valid bits to force misses
#             if rst = '1' then
        # On reset, clear all valid bits to force misses
        # TODO figure out how reset signal works in nmigeni
        with m.If("""TODO RST???"""):
# 		for i in index_t loop
            for i in range(NUM_LINES):
# 		    cache_valids(i) <= (others => '0');
                sync += cache_valid_bits[i].eq(0)
# 		end loop;

#                 r1.state <= IDLE;
#                 r1.full <= '0';
# 		  r1.slow_valid <= '0';
#                 r1.wb.cyc <= '0';
#                 r1.wb.stb <= '0';
#                 r1.ls_valid <= '0';
#                 r1.mmu_done <= '0';
            sync += r1.state.eq(State.IDLE)
            sync += r1.full.eq(0)
            sync += r1.slow_valid.eq(0)
            sync += r1.wb.cyc.eq(0)
            sync += r1.wb.stb.eq(0)
            sync += r1.ls_valid.eq(0)
            sync += r1.mmu_done.eq(0)

# 		-- Not useful normally but helps avoiding
#               -- tons of sim warnings
        # Not useful normally but helps avoiding
        # tons of sim warnings
# 		r1.wb.adr <= (others => '0');
            sync += r1.wb.adr.eq(0)
#             else
        with m.Else():
# 		  -- One cycle pulses reset
# 		  r1.slow_valid <= '0';
#                 r1.write_bram <= '0';
#                 r1.inc_acks <= '0';
#                 r1.dec_acks <= '0';
#
#                 r1.ls_valid <= '0';
#                 -- complete tlbies and TLB loads in the third cycle
#                 r1.mmu_done <= r0_valid and (r0.tlbie or r0.tlbld);
            # One cycle pulses reset
            sync += r1.slow_valid.eq(0)
            sync += r1.write_bram.eq(0)
            sync += r1.inc_acks.eq(0)
            sync += r1.dec_acks.eq(0)

            sync += r1.ls_valid.eq(0)
            # complete tlbies and TLB loads in the third cycle
            sync += r1.mmu_done.eq(r0_valid & (r0.tlbie | r0.tlbld))

#                 if req_op = OP_LOAD_HIT or req_op = OP_STCX_FAIL then
            with m.If(req_op == Op.OP_LOAD_HIT
                      | req_op == Op.OP_STCX_FAIL):
#                     if r0.mmu_req = '0' then
                with m.If(~r0.mmu_req):
#                         r1.ls_valid <= '1';
                    sync += r1.ls_valid.eq(1)
#                     else
                with m.Else():
#                         r1.mmu_done <= '1';
                    sync += r1.mmu_done.eq(1)
#                     end if;
#                 end if;

#                 if r1.write_tag = '1' then
            with m.If(r1.write_tag):
#                     -- Store new tag in selected way
#                     for i in 0 to NUM_WAYS-1 loop
                # Store new tag in selected way
                for i in range(NUM_WAYS):
#                         if i = replace_way then
                    with m.If(i == replace_way):
#                             cache_tags(r1.store_index)(
#                              (i + 1) * TAG_WIDTH - 1
#                              downto i * TAG_WIDTH
#                             ) <=
#                              (TAG_WIDTH - 1 downto TAG_BITS => '0')
#                              & r1.reload_tag;
                        sync += cache_tag[
                                 r1.store_index
                                ][i * TAG_WIDTH:(i +1) * TAG_WIDTH].eq(
                                 Const(TAG_WIDTH, TAG_WIDTH)
                                 & r1.reload_tag
                                )
#                         end if;
#                     end loop;
#                     r1.store_way <= replace_way;
#                     r1.write_tag <= '0';
                sync += r1.store_way.eq(replace_way)
                sync += r1.write_tag.eq(0)
#                 end if;

#                 -- Take request from r1.req if there is one there,
#                 -- else from req_op, ra, etc.
#                 if r1.full = '1' then
            # Take request from r1.req if there is one there,
            # else from req_op, ra, etc.
            with m.If(r1.full)
#                     req := r1.req;
                sync += req.eq(r1.req)

#                 else
            with m.Else():
#                     req.op := req_op;
#                     req.valid := req_go;
#                     req.mmu_req := r0.mmu_req;
#                     req.dcbz := r0.req.dcbz;
#                     req.real_addr := ra;
                sync += req.op.eq(req_op)
                sync += req.valid.eq(req_go)
                sync += req.mmu_req.eq(r0.mmu_req)
                sync += req.dcbz.eq(r0.req.dcbz)
                sync += req.real_addr.eq(ra)

#                     -- Force data to 0 for dcbz
#                     if r0.req.dcbz = '0' then
                with m.If(~r0.req.dcbz):
#                         req.data := r0.req.data;
                    sync += req.data.eq(r0.req.data)

#                     else
                with m.Else():
#                         req.data := (others => '0');
                    sync += req.data.eq(0)
#                     end if;

#                     -- Select all bytes for dcbz
#                     -- and for cacheable loads
#                     if r0.req.dcbz = '1'
#                      or (r0.req.load = '1' and r0.req.nc = '0') then
                # Select all bytes for dcbz
                # and for cacheable loads
                with m.If(r0.req.dcbz | (r0.req.load & ~r0.req.nc):
#                         req.byte_sel := (others => '1');
                    sync += req.byte_sel.eq(1)

#                     else
                with m.Else():
#                         req.byte_sel := r0.req.byte_sel;
                    sync += req.byte_sel.eq(r0.req.byte_sel)
#                     end if;

#                     req.hit_way := req_hit_way;
#                     req.same_tag := req_same_tag;
                sync += req.hit_way.eq(req_hit_way)
                sync += req.same_tag.eq(req_same_tag)

#                     -- Store the incoming request from r0,
#                     -- if it is a slow request
#                     -- Note that r1.full = 1 implies req_op = OP_NONE
#                     if req_op = OP_LOAD_MISS or req_op = OP_LOAD_NC
#                      or req_op = OP_STORE_MISS
#                      or req_op = OP_STORE_HIT then
                # Store the incoming request from r0,
                # if it is a slow request
                # Note that r1.full = 1 implies req_op = OP_NONE
                with m.If(req_op == Op.OP_LOAD_MISS
                          | req_op == Op.OP_LOAD_NC
                          | req_op == Op.OP_STORE_MISS
                          | req_op == Op.OP_STORE_HIT):
#                         r1.req <= req;
#                         r1.full <= '1';
                    sync += r1.req(req)
                    sync += r1.full.eq(1)
#                     end if;
#                 end if;
#
# 		-- Main state machine
# 		case r1.state is
            # Main state machine
            with m.Switch(r1.state):

#                 when IDLE =>
                with m.Case(State.IDLE)
#                     r1.wb.adr <= req.real_addr(
#                                   r1.wb.adr'left downto 0
#                                  );
#                     r1.wb.sel <= req.byte_sel;
#                     r1.wb.dat <= req.data;
#                     r1.dcbz <= req.dcbz;
#
#                     -- Keep track of our index and way
#                     -- for subsequent stores.
#                     r1.store_index <= get_index(req.real_addr);
#                     r1.store_row <= get_row(req.real_addr);
#                     r1.end_row_ix <=
#                      get_row_of_line(get_row(req.real_addr)) - 1;
#                     r1.reload_tag <= get_tag(req.real_addr);
#                     r1.req.same_tag <= '1';
                    sync += r1.wb.adr.eq(req.real_addr[0:r1.wb.adr])
                    sync += r1.wb.sel.eq(req.byte_sel)
                    sync += r1.wb.dat.eq(req.data)
                    sync += r1.dcbz.eq(req.dcbz)

                    # Keep track of our index and way
                    # for subsequent stores.
                    sync += r1.store_index.eq(get_index(req.real_addr))
                    sync += r1.store_row.eq(get_row(req.real_addr))
                    sync += r1.end_row_ix.eq(
                             get_row_of_line(get_row(req.real_addr))
                            )
                    sync += r1.reload_tag.eq(get_tag(req.real_addr))
                    sync += r1.req.same_tag.eq(1)

#                     if req.op = OP_STORE_HIT theni
                    with m.If(req.op == Op.OP_STORE_HIT):
#                         r1.store_way <= req.hit_way;
                        sync += r1.store_way.eq(req.hit_way)
#                     end if;

#                     -- Reset per-row valid bits,
#                     -- ready for handling OP_LOAD_MISS
#                     for i in 0 to ROW_PER_LINE - 1 loop
                    # Reset per-row valid bits,
                    # ready for handling OP_LOAD_MISS
                    for i in range(ROW_PER_LINE):
#                         r1.rows_valid(i) <= '0';
                        sync += r1.rows_valid[i].eq(0)
#                     end loop;

#                     case req.op is
                    with m.Switch(req.op):
#                     when OP_LOAD_HIT =>
                        with m.Case(Op.OP_LOAD_HIT):
#                         -- stay in IDLE state
                            # stay in IDLE state
                            pass

#                     when OP_LOAD_MISS =>
                        with m.Case(Op.OP_LOAD_MISS):
# 			-- Normal load cache miss,
#                       -- start the reload machine
# 			report "cache miss real addr:" &
#                        to_hstring(req.real_addr) & " idx:" &
#                        integer'image(get_index(req.real_addr)) &
# 			 " tag:" & to_hstring(get_tag(req.real_addr));
                            # Normal load cache miss,
                            # start the reload machine
                            print(f"cache miss real addr:" \
                                  f"{req_real_addr}" \
                                  f" idx:{get_index(req_real_addr)}" \
                                  f" tag:{get_tag(req.real_addr)}")

# 			-- Start the wishbone cycle
# 			r1.wb.we  <= '0';
# 			r1.wb.cyc <= '1';
# 			r1.wb.stb <= '1';
                            # Start the wishbone cycle
                            sync += r1.wb.we.eq(0)
                            sync += r1.wb.cyc.eq(1)
                            sync += r1.wb.stb.eq(1)

# 			-- Track that we had one request sent
# 			r1.state <= RELOAD_WAIT_ACK;
#                       r1.write_tag <= '1';
                            # Track that we had one request sent
                            sync += r1.state.eq(State.RELOAD_WAIT_ACK)
                            sync += r1.write_tag.eq(1)

# 		    when OP_LOAD_NC =>
                        with m.Case(Op.OP_LOAD_NC):
#                       r1.wb.cyc <= '1';
#                       r1.wb.stb <= '1';
# 			r1.wb.we <= '0';
# 			r1.state <= NC_LOAD_WAIT_ACK;
                            sync += r1.wb.cyc.eq(1)
                            sync += r1.wb.stb.eq(1)
                            sync += r1.wb.we.eq(0)
                            sync += r1.state.eq(State.NC_LOAD_WAIT_ACK)

#                     when OP_STORE_HIT | OP_STORE_MISS =>
                        with m.Case(Op.OP_STORE_HIT
                                    | Op.OP_STORE_MISS):
#                         if req.dcbz = '0' then
                            with m.If(~req.bcbz):
#                             r1.state <= STORE_WAIT_ACK;
#                             r1.acks_pending <= to_unsigned(1, 3);
#                             r1.full <= '0';
#                             r1.slow_valid <= '1';
                                sync += r1.state.eq(
                                         State.STORE_WAIT_ACK
                                        )
                                sync += r1.acks_pending.eq(
                                         '''TODO to_unsignes(1,3)'''
                                        )
                                sync += r1.full.eq(0)
                                sync += r1.slow_valid.eq(1)

#                             if req.mmu_req = '0' then
                                with m.If(~req.mmu_req):
#                                 r1.ls_valid <= '1';
                                    sync += r1.ls_valid.eq(1)
#                             else
                                with m.Else():
#                                 r1.mmu_done <= '1';
                                    sync += r1.mmu_done.eq(1)
#                             end if;

#                             if req.op = OP_STORE_HIT then
                                with m.If(req.op == Op.OP_STORE_HIT):
#                                 r1.write_bram <= '1';
                                    sync += r1.write_bram.eq(1)
#                             end if;

#                         else
                            with m.Else():
#                             -- dcbz is handled much like a load
#                             -- miss except that we are writing
#                             -- to memory instead of reading
#                             r1.state <= RELOAD_WAIT_ACK;
                                # dcbz is handled much like a load
                                # miss except that we are writing
                                # to memory instead of reading
                                sync += r1.state.eq(Op.RELOAD_WAIT_ACK)

#                             if req.op = OP_STORE_MISS then
                                with m.If(req.op == Op.OP_STORE_MISS):
#                                 r1.write_tag <= '1';
                                    sync += r1.write_tag.eq(1)
#                             end if;
#                         end if;

#                         r1.wb.we <= '1';
#                         r1.wb.cyc <= '1';
#                         r1.wb.stb <= '1';
                            sync += r1.wb.we.eq(1)
                            sync += r1.wb.cyc.eq(1)
                            sync += r1.wb.stb.eq(1)

# 		    -- OP_NONE and OP_BAD do nothing
#                   -- OP_BAD & OP_STCX_FAIL were handled above already
# 		    when OP_NONE =>
#                     when OP_BAD =>
#                     when OP_STCX_FAIL =>
                        # OP_NONE and OP_BAD do nothing
                        # OP_BAD & OP_STCX_FAIL were
                        # handled above already
                        with m.Case(Op.OP_NONE):
                            pass

                        with m.Case(OP_BAD):
                            pass

                        with m.Case(OP_STCX_FAIL):
                            pass
# 		    end case;

#                 when RELOAD_WAIT_ACK =>
                    with m.Case(State.RELOAD_WAIT_ACK):
#                     -- Requests are all sent if stb is 0
                        # Requests are all sent if stb is 0
                        sync += stbs_done.eq(~r1.wb.stb)
# 		    stbs_done := r1.wb.stb = '0';

# 		    -- If we are still sending requests,
#                   -- was one accepted?
# 		    if wishbone_in.stall = '0' and not stbs_done then
                        # If we are still sending requests,
                        # was one accepted?
                        with m.If(~wb_in.stall & ~stbs_done):
# 			-- That was the last word ? We are done sending.
#                       -- Clear stb and set stbs_done so we can handle
#                       -- an eventual last ack on the same cycle.
# 			if is_last_row_addr(
#                        r1.wb.adr, r1.end_row_ix
#                       ) then
                            # That was the last word?
                            # We are done sending.
                            # Clear stb and set stbs_done
                            # so we can handle an eventual
                            # last ack on the same cycle.
                            with m.If(is_last_row_addr(
                                      r1.wb.adr, r1.end_row_ix)):
# 			    r1.wb.stb <= '0';
# 			    stbs_done := true;
                                sync += r1.wb.stb.eq(0)
                                sync += stbs_done.eq(0)
# 			end if;

# 			-- Calculate the next row address
# 			r1.wb.adr <= next_row_addr(r1.wb.adr);
                            # Calculate the next row address
                            sync += r1.wb.adr.eq(next_row_addr(r1.wb.adr))
# 		    end if;

# 		    -- Incoming acks processing
#                     r1.forward_valid1 <= wishbone_in.ack;
                        # Incoming acks processing
                        sync += r1.forward_valid1.eq(wb_in.ack)

# 		    if wishbone_in.ack = '1' then
                        with m.If(wb_in.ack):
#                         r1.rows_valid(
#                          r1.store_row mod ROW_PER_LINE
#                         ) <= '1';
                            sync += r1.rows_valid[
                                     r1.store_row % ROW_PER_LINE
                                    ].eq(1)

#                         -- If this is the data we were looking for,
#                         -- we can complete the request next cycle.
#                         -- Compare the whole address in case the
#                         -- request in r1.req is not the one that
#                         -- started this refill.
# 			if r1.full = '1' and r1.req.same_tag = '1'
#                        and ((r1.dcbz = '1' and r1.req.dcbz = '1')
#                        or (r1.dcbz = '0' and r1.req.op = OP_LOAD_MISS))
#                        and r1.store_row = get_row(r1.req.real_addr) then
                            # If this is the data we were looking for,
                            # we can complete the request next cycle.
                            # Compare the whole address in case the
                            # request in r1.req is not the one that
                            # started this refill.
                            with m.If(r1.full & r1.req.same_tag &
                                      ((r1.dcbz & r1.req.dcbz)
                                       (~r1.dcbz &
                                        r1.req.op == Op.OP_LOAD_MISS)
                                       ) &
                                       r1.store_row
                                       == get_row(r1.req.real_addr):
#                             r1.full <= '0';
#                             r1.slow_valid <= '1';
                                sync += r1.full.eq(0)
                                sync += r1.slow_valid.eq(1)

#                             if r1.mmu_req = '0' then
                                    with m.If(~r1.mmu_req):
#                                 r1.ls_valid <= '1';
                                        sync += r1.ls_valid.eq(1)
#                             else
                                    with m.Else():
#                                 r1.mmu_done <= '1';
                                        sync += r1.mmu_done.eq(1)
#                             end if;
#                             r1.forward_sel <= (others => '1');
#                             r1.use_forward1 <= '1';
                                sync += r1.forward_sel.eq(1)
                                sync += r1.use_forward1.eq(1)
# 			end if;

# 			-- Check for completion
# 			if stbs_done and is_last_row(r1.store_row,
#                        r1.end_row_ix) then
                            # Check for completion
                            with m.If(stbs_done &
                                      is_last_row(r1.store_row,
                                      r1.end_row_ix)):

# 			    -- Complete wishbone cycle
# 			    r1.wb.cyc <= '0';
                                # Complete wishbone cycle
                                sync += r1.wb.cyc.eq(0)

# 			    -- Cache line is now valid
# 			    cache_valids(r1.store_index)(
#                            r1.store_way
#                           ) <= '1';
                                # Cache line is now valid
                                sync += cache_valid_bits[
                                         r1.store_index
                                        ][r1.store_way].eq(1)

#                           r1.state <= IDLE;
                                sync += r1.state.eq(State.IDLE)
# 			end if;

# 			-- Increment store row counter
# 			r1.store_row <= next_row(r1.store_row);
                            # Increment store row counter
                            sync += r1.store_row.eq(next_row(
                                     r1.store_row
                                    ))
# 		    end if;

#                 when STORE_WAIT_ACK =>
                    with m.Case(State.STORE_WAIT_ACK):
#                     stbs_done := r1.wb.stb = '0';
#                     acks := r1.acks_pending;
                        sync += stbs_done.eq(~r1.wb.stb)
                        sync += acks.eq(r1.acks_pending)

#                     if r1.inc_acks /= r1.dec_acks then
                        with m.If(r1.inc_acks != r1.dec_acks):

#                         if r1.inc_acks = '1' then
                            with m.If(r1.inc_acks):
#                             acks := acks + 1;
                                sync += acks.eq(acks + 1)

#                         else
                            with m.Else():
#                             acks := acks - 1;
                                sync += acks.eq(acks - 1)
#                         end if;
#                     end if;

#                     r1.acks_pending <= acks;
                        sync += r1.acks_pending.eq(acks)

# 		      -- Clear stb when slave accepted request
#                     if wishbone_in.stall = '0' then
                        # Clear stb when slave accepted request
                        with m.If(~wb_in.stall):
#                         -- See if there is another store waiting
#                         -- to be done which is in the same real page.
#                         if req.valid = '1' then
                            # See if there is another store waiting
                            # to be done which is in the same real page.
                            with m.If(req.valid):
#                             r1.wb.adr(
#                              SET_SIZE_BITS - 1 downto 0
#                             ) <= req.real_addr(
#                              SET_SIZE_BITS - 1 downto 0
#                             );
#                             r1.wb.dat <= req.data;
#                             r1.wb.sel <= req.byte_sel;
                                sync += r1.wb.adr[0:SET_SIZE_BITS].eq(
                                         req.real_addr[0:SET_SIZE_BITS]
                                        )
#                         end if;

#                         if acks < 7 and req.same_tag = '1'
#                          and (req.op = OP_STORE_MISS
#                          or req.op = OP_STORE_HIT) then
                            with m.Elif(acks < 7 & req.same_tag &
                                        (req.op == Op.Op_STORE_MISS
                                         | req.op == Op.OP_SOTRE_HIT)):
#                             r1.wb.stb <= '1';
#                             stbs_done := false;
                                sync += r1.wb.stb.eq(1)
                                sync += stbs_done.eq(0)

#                             if req.op = OP_STORE_HIT then
                                with m.If(req.op == Op.OP_STORE_HIT):
#                                 r1.write_bram <= '1';
                                    sync += r1.write_bram.eq(1)
#                             end if;
#                             r1.full <= '0';
#                             r1.slow_valid <= '1';
                                sync += r1.full.eq(0)
                                sync += r1.slow_valid.eq(1)

#                             -- Store requests never come from the MMU
#                             r1.ls_valid <= '1';
#                             stbs_done := false;
#                             r1.inc_acks <= '1';
                                # Store request never come from the MMU
                                sync += r1.ls_valid.eq(1)
                                sync += stbs_done.eq(0)
                                sync += r1.inc_acks.eq(1)
#                         else
                            with m.Else():
#                             r1.wb.stb <= '0';
#                             stbs_done := true;
                                sync += r1.wb.stb.eq(0)
                                sync += stbs_done.eq(1)
#                         end if;
# 		    end if;

# 		    -- Got ack ? See if complete.
# 		    if wishbone_in.ack = '1' then
                        # Got ack ? See if complete.
                        with m.If(wb_in.ack):
#                         if stbs_done and acks = 1 then
                            with m.If(stbs_done & acks)
#                             r1.state <= IDLE;
#                             r1.wb.cyc <= '0';
#                             r1.wb.stb <= '0';
                                sync += r1.state.eq(State.IDLE)
                                sync += r1.wb.cyc.eq(0)
                                sync += r1.wb.stb.eq(0)
#                         end if;
#                         r1.dec_acks <= '1';
                            sync += r1.dec_acks.eq(1)
# 		    end if;

#                 when NC_LOAD_WAIT_ACK =>
                    with m.Case(State.NC_LOAD_WAIT_ACK):
# 		    -- Clear stb when slave accepted request
#                     if wishbone_in.stall = '0' then
                        # Clear stb when slave accepted request
                        with m.If(~wb_in.stall):
# 			r1.wb.stb <= '0';
                            sync += r1.wb.stb.eq(0)
# 		    end if;

# 		    -- Got ack ? complete.
# 		    if wishbone_in.ack = '1' then
                        # Got ack ? complete.
                        with m.If(wb_in.ack):
#                         r1.state <= IDLE;
#                         r1.full <= '0';
# 			  r1.slow_valid <= '1';
                            sync += r1.state.eq(State.IDLE)
                            sync += r1.full.eq(0)
                            sync += r1.slow_valid.eq(1)

#                         if r1.mmu_req = '0' then
                            with m.If(~r1.mmu_req):
#                             r1.ls_valid <= '1';
                                sync += r1.ls_valid.eq(1)

#                         else
                            with m.Else():
#                             r1.mmu_done <= '1';
                                sync += r1.mmu_done.eq(1)
#                         end if;

#                         r1.forward_sel <= (others => '1');
#                         r1.use_forward1 <= '1';
# 			  r1.wb.cyc <= '0';
# 			  r1.wb.stb <= '0';
                            sync += r1.forward_sel.eq(1)
                            sync += r1.use_forward1.eq(1)
                            sync += r1.wb.cyc.eq(0)
                            sync += r1.wb.stb.eq(0)
# 		    end if;
#                 end case;
# 	    end if;
# 	end if;
#     end process;

#     dc_log: if LOG_LENGTH > 0 generate
# TODO learn how to tranlate vhdl generate into nmigen
    def dcache_log(self, r1, valid_ra, tlb_hit_way, stall_out,
                   d_out, wb_in, log_out):

        comb = m.d.comb
        sync = m.d.sync

#         signal log_data : std_ulogic_vector(19 downto 0);
        log_data = Signal(20)

        comb += log_data

#     begin
#         dcache_log: process(clk)
#         begin
#             if rising_edge(clk) then
#                 log_data <= r1.wb.adr(5 downto 3) &
#                             wishbone_in.stall &
#                             wishbone_in.ack &
#                             r1.wb.stb & r1.wb.cyc &
#                             d_out.error &
#                             d_out.valid &
#                             std_ulogic_vector(
#                              to_unsigned(op_t'pos(req_op), 3)) &
#                             stall_out &
#                             std_ulogic_vector(
#                              to_unsigned(tlb_hit_way, 3)) &
#                             valid_ra &
#                             std_ulogic_vector(
#                              to_unsigned(state_t'pos(r1.state), 3));
        sync += log_data.eq(Cat(
                 Const(r1.state, 3), valid_ra, Const(tlb_hit_way, 3),
                 stall_out, Const(req_op, 3), d_out.valid, d_out.error,
                 r1.wb.cyc, r1.wb.stb, wb_in.ack, wb_in.stall,
                 r1.wb.adr[3:6]
                ))
#             end if;
#         end process;
#         log_out <= log_data;
    # TODO ??? I am very confused need help
    comb += log_out.eq(log_data)
#     end generate;
# end;

    def elaborate(self, platform):
        LINE_SIZE    = self.LINE_SIZE
        NUM_LINES    = self.NUM_LINES
        NUM_WAYS     = self.NUM_WAYS
        TLB_SET_SIZE = self.TLB_SET_SIZE
        TLB_NUM_WAYS = self.TLB_NUM_WAYS
        TLB_LG_PGSZ  = self.TLB_LG_PGSZ
        LOG_LENGTH   = self.LOG_LENGTH

        # BRAM organisation: We never access more than
        #     -- wishbone_data_bits at a time so to save
        #     -- resources we make the array only that wide, and
        #     -- use consecutive indices for to make a cache "line"
        #     --
        #     -- ROW_SIZE is the width in bytes of the BRAM
        #     -- (based on WB, so 64-bits)
        ROW_SIZE = WB_DATA_BITS / 8;

        # ROW_PER_LINE is the number of row (wishbone
        # transactions) in a line
        ROW_PER_LINE = LINE_SIZE // ROW_SIZE

        # BRAM_ROWS is the number of rows in BRAM needed
        # to represent the full dcache
        BRAM_ROWS = NUM_LINES * ROW_PER_LINE


        # Bit fields counts in the address

        # REAL_ADDR_BITS is the number of real address
        # bits that we store
        REAL_ADDR_BITS = 56

        # ROW_BITS is the number of bits to select a row
        ROW_BITS = log2_int(BRAM_ROWS)

        # ROW_LINE_BITS is the number of bits to select
        # a row within a line
        ROW_LINE_BITS = log2_int(ROW_PER_LINE)

        # LINE_OFF_BITS is the number of bits for
        # the offset in a cache line
        LINE_OFF_BITS = log2_int(LINE_SIZE)

        # ROW_OFF_BITS is the number of bits for
        # the offset in a row
        ROW_OFF_BITS = log2_int(ROW_SIZE)

        # INDEX_BITS is the number if bits to
        # select a cache line
        INDEX_BITS = log2_int(NUM_LINES)

        # SET_SIZE_BITS is the log base 2 of the set size
        SET_SIZE_BITS = LINE_OFF_BITS + INDEX_BITS

        # TAG_BITS is the number of bits of
        # the tag part of the address
        TAG_BITS = REAL_ADDR_BITS - SET_SIZE_BITS

        # TAG_WIDTH is the width in bits of each way of the tag RAM
        TAG_WIDTH = TAG_BITS + 7 - ((TAG_BITS + 7) % 8)

        # WAY_BITS is the number of bits to select a way
        WAY_BITS = log2_int(NUM_WAYS)

        # Example of layout for 32 lines of 64 bytes:
        #
        # ..  tag    |index|  line  |
        # ..         |   row   |    |
        # ..         |     |---|    | ROW_LINE_BITS  (3)
        # ..         |     |--- - --| LINE_OFF_BITS (6)
        # ..         |         |- --| ROW_OFF_BITS  (3)
        # ..         |----- ---|    | ROW_BITS      (8)
        # ..         |-----|        | INDEX_BITS    (5)
        # .. --------|              | TAG_BITS      (45)

        TAG_RAM_WIDTH = TAG_WIDTH * NUM_WAYS

        def CacheTagArray():
            return Array(CacheTagSet() for x in range(NUM_LINES))

        def CacheValidBitsArray():
            return Array(CacheWayValidBits() for x in range(NUM_LINES))

        def RowPerLineValidArray():
            return Array(Signal() for x in range(ROW_PER_LINE))

        # Storage. Hopefully "cache_rows" is a BRAM, the rest is LUTs
        cache_tags       = CacheTagArray()
        cache_tag_set    = Signal(TAG_RAM_WIDTH)
        cache_valid_bits = CacheValidBitsArray()

        # TODO attribute ram_style : string;
        # TODO attribute ram_style of cache_tags : signal is "distributed";

        # L1 TLB
        TLB_SET_BITS     = log2_int(TLB_SET_SIZE)
        TLB_WAY_BITS     = log2_int(TLB_NUM_WAYS)
        TLB_EA_TAG_BITS  = 64 - (TLB_LG_PGSZ + TLB_SET_BITS)
        TLB_TAG_WAY_BITS = TLB_NUM_WAYS * TLB_EA_TAG_BITS
        TLB_PTE_BITS     = 64
        TLB_PTE_WAY_BITS = TLB_NUM_WAYS * TLB_PTE_BITS;

        def TLBValidBitsArray():
            return Array(
             Signal(TLB_NUM_WAYS) for x in range(TLB_SET_SIZE)
            )

        def TLBTagsArray():
            return Array(
             Signal(TLB_TAG_WAY_BITS) for x in range (TLB_SET_SIZE)
            )

        def TLBPtesArray():
            return Array(
             Signal(TLB_PTE_WAY_BITS) for x in range(TLB_SET_SIZE)
            )

        def HitWaySet():
            return Array(Signal(NUM_WAYS) for x in range(TLB_NUM_WAYS))

"""note: these are passed to nmigen.hdl.Memory as "attributes".
   don't know how, just that they are.
"""
        dtlb_valid_bits = TLBValidBitsArray()
        dtlb_tags       = TLBTagsArray()
        dtlb_ptes       = TLBPtesArray()
        # TODO attribute ram_style of
        #  dtlb_tags : signal is "distributed";
        # TODO attribute ram_style of
        #  dtlb_ptes : signal is "distributed";

        r0      = RegStage0()
        r0_full = Signal()

        r1 = RegStage1()

        reservation = Reservation()

        # Async signals on incoming request
        req_index    = Signal(NUM_LINES)
        req_row      = Signal(BRAM_ROWS)
        req_hit_way  = Signal(WAY_BITS)
        req_tag      = Signal(TAG_BITS)
        req_op       = Op()
        req_data     = Signal(64)
        req_same_tag = Signal()
        req_go       = Signal()

        early_req_row     = Signal(BRAM_ROWS)

        cancel_store      = Signal()
        set_rsrv          = Signal()
        clear_rsrv        = Signal()

        r0_valid          = Signal()
        r0_stall          = Signal()

        use_forward1_next = Signal()
        use_forward2_next = Signal()

        # Cache RAM interface
        def CacheRamOut():
            return Array(Signal(WB_DATA_BITS) for x in range(NUM_WAYS))

        cache_out         = CacheRamOut()

        # PLRU output interface
        def PLRUOut():
            return Array(Signal(WAY_BITS) for x in range(Index()))

        plru_victim       = PLRUOut()
        replace_way       = Signal(WAY_BITS)

        # Wishbone read/write/cache write formatting signals
        bus_sel           = Signal(8)

        # TLB signals
        tlb_tag_way   = Signal(TLB_TAG_WAY_BITS)
        tlb_pte_way   = Signal(TLB_PTE_WAY_BITS)
        tlb_valid_way = Signal(TLB_NUM_WAYS)
        tlb_req_index = Signal(TLB_SET_SIZE)
        tlb_hit       = Signal()
        tlb_hit_way   = Signal(TLB_NUM_WAYS)
        pte           = Signal(TLB_PTE_BITS)
        ra            = Signal(REAL_ADDR_BITS)
        valid_ra      = Signal()
        perm_attr     = PermAttr()
        rc_ok         = Signal()
        perm_ok       = Signal()
        access_ok     = Signal()

        # TLB PLRU output interface
        def TLBPLRUOut():
            return Array(
                Signal(TLB_WAY_BITS) for x in range(TLB_SET_SIZE)
            )

        tlb_plru_victim = TLBPLRUOut()

        # Helper functions to decode incoming requests
        #
        # Return the cache line index (tag index) for an address
        def get_index(addr):
            return addr[LINE_OFF_BITS:SET_SIZE_BITS]

        # Return the cache row index (data memory) for an address
        def get_row(addr):
            return addr[ROW_OFF_BITS:SET_SIZE_BITS]

        # Return the index of a row within a line
        def get_row_of_line(row):
            row_v = Signal(ROW_BITS)
            row_v = Signal(row)
            return row_v[0:ROW_LINE_BITS]

        # Returns whether this is the last row of a line
        def is_last_row_addr(addr, last):
            return addr[ROW_OFF_BITS:LINE_OFF_BITS] == last

        # Returns whether this is the last row of a line
        def is_last_row(row, last):
            return get_row_of_line(row) == last

        # Return the address of the next row in the current cache line
        def next_row_addr(addr):
            row_idx = Signal(ROW_LINE_BITS)
            result  = WBAddrType()
            # Is there no simpler way in VHDL to
            # generate that 3 bits adder ?
            row_idx = addr[ROW_OFF_BITS:LINE_OFF_BITS]
            row_idx = Signal(row_idx + 1)
            result = addr
            result[ROW_OFF_BITS:LINE_OFF_BITS] = row_idx
            return result

        # Return the next row in the current cache line. We use a
        # dedicated function in order to limit the size of the
        # generated adder to be only the bits within a cache line
        # (3 bits with default settings)
        def next_row(row)
            row_v   = Signal(ROW_BITS)
            row_idx = Signal(ROW_LINE_BITS)
            result  = Signal(ROW_BITS)

            row_v = Signal(row)
            row_idx = row_v[ROW_LINE_BITS]
            row_v[0:ROW_LINE_BITS] = Signal(row_idx + 1)
            return row_v

        # Get the tag value from the address
        def get_tag(addr):
            return addr[SET_SIZE_BITS:REAL_ADDR_BITS]

        # Read a tag from a tag memory row
        def read_tag(way, tagset):
            return tagset[way *TAG_WIDTH:way * TAG_WIDTH + TAG_BITS]

        # Read a TLB tag from a TLB tag memory row
        def read_tlb_tag(way, tags):
            j = Signal()

            j = way * TLB_EA_TAG_BITS
            return tags[j:j + TLB_EA_TAG_BITS]

        # Write a TLB tag to a TLB tag memory row
        def write_tlb_tag(way, tags), tag):
            j = Signal()

            j = way * TLB_EA_TAG_BITS
            tags[j:j + TLB_EA_TAG_BITS] = tag

        # Read a PTE from a TLB PTE memory row
        def read_tlb_pte(way, ptes):
            j = Signal()

            j = way * TLB_PTE_BITS
            return ptes[j:j + TLB_PTE_BITS]

        def write_tlb_pte(way, ptes,newpte):
            j = Signal()

            j = way * TLB_PTE_BITS
            return ptes[j:j + TLB_PTE_BITS] = newpte

        assert (LINE_SIZE % ROW_SIZE) == 0 "LINE_SIZE not " \
         "multiple of ROW_SIZE"

        assert (LINE_SIZE % 2) == 0 "LINE_SIZE not power of 2"

        assert (NUM_LINES % 2) == 0 "NUM_LINES not power of 2"

        assert (ROW_PER_LINE % 2) == 0 "ROW_PER_LINE not" \
         "power of 2"

        assert ROW_BITS == (INDEX_BITS + ROW_LINE_BITS) \
         "geometry bits don't add up"

        assert (LINE_OFF_BITS = ROW_OFF_BITS + ROW_LINEBITS) \
         "geometry bits don't add up"

        assert REAL_ADDR_BITS == (TAG_BITS + INDEX_BITS \
         + LINE_OFF_BITS) "geometry bits don't add up"

        assert REAL_ADDR_BITS == (TAG_BITS + ROW_BITS + ROW_OFF_BITS) \
         "geometry bits don't add up"

        assert 64 == wishbone_data_bits "Can't yet handle a" \
         "wishbone width that isn't 64-bits"

        assert SET_SIZE_BITS <= TLB_LG_PGSZ "Set indexed by" \
         "virtual address"

        # we don't yet handle collisions between loadstore1 requests
        # and MMU requests
        comb += m_out.stall.eq(0)

        # Hold off the request in r0 when r1 has an uncompleted request
        comb += r0_stall.eq(r0_full & r1.full)
        comb += r0_valid.eq(r0_full & ~r1.full)
        comb += stall_out.eq(r0_stall)

        # Wire up wishbone request latch out of stage 1
        comb += wishbone_out.eq(r1.wb)



# dcache_tb.vhdl
#
# entity dcache_tb is
# end dcache_tb;
#
# architecture behave of dcache_tb is
#     signal clk          : std_ulogic;
#     signal rst          : std_ulogic;
#
#     signal d_in         : Loadstore1ToDcacheType;
#     signal d_out        : DcacheToLoadstore1Type;
#
#     signal m_in         : MmuToDcacheType;
#     signal m_out        : DcacheToMmuType;
#
#     signal wb_bram_in   : wishbone_master_out;
#     signal wb_bram_out  : wishbone_slave_out;
#
#     constant clk_period : time := 10 ns;
# begin
#     dcache0: entity work.dcache
#         generic map(
#
#             LINE_SIZE => 64,
#             NUM_LINES => 4
#             )
#         port map(
#             clk => clk,
#             rst => rst,
#             d_in => d_in,
#             d_out => d_out,
#             m_in => m_in,
#             m_out => m_out,
#             wishbone_out => wb_bram_in,
#             wishbone_in => wb_bram_out
#             );
#
#     -- BRAM Memory slave
#     bram0: entity work.wishbone_bram_wrapper
#         generic map(
#             MEMORY_SIZE   => 1024,
#             RAM_INIT_FILE => "icache_test.bin"
#             )
#         port map(
#             clk => clk,
#             rst => rst,
#             wishbone_in => wb_bram_in,
#             wishbone_out => wb_bram_out
#             );
#
#     clk_process: process
#     begin
#         clk <= '0';
#         wait for clk_period/2;
#         clk <= '1';
#         wait for clk_period/2;
#     end process;
#
#     rst_process: process
#     begin
#         rst <= '1';
#         wait for 2*clk_period;
#         rst <= '0';
#         wait;
#     end process;
#
#     stim: process
#     begin
#     -- Clear stuff
#     d_in.valid <= '0';
#     d_in.load <= '0';
#     d_in.nc <= '0';
#     d_in.addr <= (others => '0');
#     d_in.data <= (others => '0');
#         m_in.valid <= '0';
#         m_in.addr <= (others => '0');
#         m_in.pte <= (others => '0');
#
#         wait for 4*clk_period;
#     wait until rising_edge(clk);
#
#     -- Cacheable read of address 4
#     d_in.load <= '1';
#     d_in.nc <= '0';
#         d_in.addr <= x"0000000000000004";
#         d_in.valid <= '1';
#     wait until rising_edge(clk);
#         d_in.valid <= '0';
#
#     wait until rising_edge(clk) and d_out.valid = '1';
#         assert d_out.data = x"0000000100000000"
#         report "data @" & to_hstring(d_in.addr) &
#         "=" & to_hstring(d_out.data) &
#         " expected 0000000100000000"
#         severity failure;
# --      wait for clk_period;
#
#     -- Cacheable read of address 30
#     d_in.load <= '1';
#     d_in.nc <= '0';
#         d_in.addr <= x"0000000000000030";
#         d_in.valid <= '1';
#     wait until rising_edge(clk);
#         d_in.valid <= '0';
#
#     wait until rising_edge(clk) and d_out.valid = '1';
#         assert d_out.data = x"0000000D0000000C"
#         report "data @" & to_hstring(d_in.addr) &
#         "=" & to_hstring(d_out.data) &
#         " expected 0000000D0000000C"
#         severity failure;
#
#     -- Non-cacheable read of address 100
#     d_in.load <= '1';
#     d_in.nc <= '1';
#         d_in.addr <= x"0000000000000100";
#         d_in.valid <= '1';
#     wait until rising_edge(clk);
#     d_in.valid <= '0';
#     wait until rising_edge(clk) and d_out.valid = '1';
#         assert d_out.data = x"0000004100000040"
#         report "data @" & to_hstring(d_in.addr) &
#         "=" & to_hstring(d_out.data) &
#         " expected 0000004100000040"
#         severity failure;
#
#     wait until rising_edge(clk);
#     wait until rising_edge(clk);
#     wait until rising_edge(clk);
#     wait until rising_edge(clk);
#
#     std.env.finish;
#     end process;
# end;
def dcache_sim(dut):
    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.adrr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield
    # wait_until rising_edge(clk)
    yield
    # Cacheable read of address 4
    yield dut.d_in.load.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(Const(0x0000000000000004, 64))
    yield dut.d_in.valid.eq(1)
    # wait-until rising_edge(clk)
    yield
    yield dut.d_in.valid.eq(0)
    yield
    while not (yield dut.d_out.valid):
        yield
    assert dut.d_out.data == Const(0x0000000100000000, 64) f"data @" \
        f"{dut.d_in.addr}={dut.d_in.data} expected 0000000100000000" \
        " -!- severity failure"


    # Cacheable read of address 30
    yield dut.d_in.load.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(Const(0x0000000000000030, 64))
    yield dut.d_in.valid.eq(1)
    yield
    yield dut.d_in.valid.eq(0)
    yield
    while not (yield dut.d_out.valid):
        yield
    assert dut.d_out.data == Const(0x0000000D0000000C, 64) f"data @" \
        f"{dut.d_in.addr}={dut.d_out.data} expected 0000000D0000000C" \
        f"-!- severity failure"

    # Non-cacheable read of address 100
    yield dut.d_in.load.eq(1)
    yield dut.d_in.nc.eq(1)
    yield dut.d_in.addr.eq(Const(0x0000000000000100, 64))
    yield dut.d_in.valid.eq(1)
    yield
    yield dut.d_in.valid.eq(0)
    yield
    while not (yield dut.d_out.valid):
        yield
    assert dut.d_out.data == Const(0x0000004100000040, 64) f"data @" \
        f"{dut.d_in.addr}={dut.d_out.data} expected 0000004100000040" \
        f"-!- severity failure"

    yield
    yield
    yield
    yield


def test_dcache():
    dut = Dcache()
    vl = rtlil.convert(dut, ports=[])
    with open("test_dcache.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcache_sim(), vcd_name='test_dcache.vcd')

if __name__ == '__main__':
    test_dcache()

