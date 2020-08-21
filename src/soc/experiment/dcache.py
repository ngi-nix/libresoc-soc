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
                                WbMasterOut, WBSlaveOut, WBMasterOutVector,
                                WBSlaveOutVector, WBIOMasterOut,
                                WBIOSlaveOut

# --
# -- Set associative dcache write-through
# --
# -- TODO (in no specific order):
# --
# -- * See list in icache.vhdl
# -- * Complete load misses on the cycle when WB data comes instead of
# --   at the end of line (this requires dealing with requests coming in
# --   while not idle...)
# --
# library ieee;
# use ieee.std_logic_1164.all;
# use ieee.numeric_std.all;
#
# library work;
# use work.utils.all;
# use work.common.all;
# use work.helpers.all;
# use work.wishbone_types.all;
#
# entity dcache is
class Dcache(Elaboratable):
#     generic (
#         -- Line size in bytes
#         LINE_SIZE : positive := 64;
#         -- Number of lines in a set
#         NUM_LINES : positive := 32;
#         -- Number of ways
#         NUM_WAYS  : positive := 4;
#         -- L1 DTLB entries per set
#         TLB_SET_SIZE : positive := 64;
#         -- L1 DTLB number of sets
#         TLB_NUM_WAYS : positive := 2;
#         -- L1 DTLB log_2(page_size)
#         TLB_LG_PGSZ : positive := 12;
#         -- Non-zero to enable log data collection
#         LOG_LENGTH : natural := 0
#         );
    def __init__(self):
        # Line size in bytes
        self.LINE_SIZE = 64
        # Number of lines in a set
        self.NUM_LINES = 32
        # Number of ways
        self.NUM_WAYS = 4
        # L1 DTLB entries per set
        self.TLB_SET_SIZE = 64
        # L1 DTLB number of sets
        self.TLB_NUM_WAYS = 2
        # L1 DTLB log_2(page_size)
        self.TLB_LG_PGSZ = 12
        # Non-zero to enable log data collection
        self.LOG_LENGTH = 0
#     port (
#         clk          : in std_ulogic;
#         rst          : in std_ulogic;
#
#         d_in         : in Loadstore1ToDcacheType;
#         d_out        : out DcacheToLoadstore1Type;
#
#         m_in         : in MmuToDcacheType;
#         m_out        : out DcacheToMmuType;
#
# 	stall_out    : out std_ulogic;
#
#         wishbone_out : out wishbone_master_out;
#         wishbone_in  : in wishbone_slave_out;
#
#         log_out      : out std_ulogic_vector(19 downto 0)
#         );
        self.d_in      = LoadStore1ToDcacheType()
        self.d_out     = DcacheToLoadStore1Type()

        self.m_in      = MmuToDcacheType()
        self.m_out     = DcacheToMmuType()

        self.stall_out = Signal()

        self.wb_out    = WBMasterOut()
        self.wb_in     = WBSlaveOut()

        self.log_out   = Signal(20)
# end entity dcache;

# architecture rtl of dcache is
    def elaborate(self, platform):
        LINE_SIZE    = self.LINE_SIZE
        NUM_LINES    = self.NUM_LINES
        NUM_WAYS     = self.NUM_WAYS
        TLB_SET_SIZE = self.TLB_SET_SIZE
        TLB_NUM_WAYS = self.TLB_NUM_WAYS
        TLB_LG_PGSZ  = self.TLB_LG_PGSZ
        LOG_LENGTH   = self.LOG_LENGTH

#     -- BRAM organisation: We never access more than
#     -- wishbone_data_bits at a time so to save
#     -- resources we make the array only that wide, and
#     -- use consecutive indices for to make a cache "line"
#     --
#     -- ROW_SIZE is the width in bytes of the BRAM
#     -- (based on WB, so 64-bits)
#     constant ROW_SIZE : natural := wishbone_data_bits / 8;
        # BRAM organisation: We never access more than
        #     -- wishbone_data_bits at a time so to save
        #     -- resources we make the array only that wide, and
        #     -- use consecutive indices for to make a cache "line"
        #     --
        #     -- ROW_SIZE is the width in bytes of the BRAM
        #     -- (based on WB, so 64-bits)
        ROW_SIZE = WB_DATA_BITS / 8;

#     -- ROW_PER_LINE is the number of row (wishbone
#     -- transactions) in a line
#     constant ROW_PER_LINE  : natural := LINE_SIZE / ROW_SIZE;
#     -- BRAM_ROWS is the number of rows in BRAM needed
#     -- to represent the full dcache
#     constant BRAM_ROWS : natural := NUM_LINES * ROW_PER_LINE;
        # ROW_PER_LINE is the number of row (wishbone
        # transactions) in a line
        ROW_PER_LINE = LINE_SIZE / ROW_SIZE
        # BRAM_ROWS is the number of rows in BRAM needed
        # to represent the full dcache
        BRAM_ROWS = NUM_LINES * ROW_PER_LINE

#     -- Bit fields counts in the address
#
#     -- REAL_ADDR_BITS is the number of real address
#     -- bits that we store
#     constant REAL_ADDR_BITS : positive := 56;
#     -- ROW_BITS is the number of bits to select a row
#     constant ROW_BITS      : natural := log2(BRAM_ROWS);
#     -- ROW_LINEBITS is the number of bits to select
#     -- a row within a line
#     constant ROW_LINEBITS  : natural := log2(ROW_PER_LINE);
#     -- LINE_OFF_BITS is the number of bits for
#     -- the offset in a cache line
#     constant LINE_OFF_BITS : natural := log2(LINE_SIZE);
#     -- ROW_OFF_BITS is the number of bits for
#     -- the offset in a row
#     constant ROW_OFF_BITS : natural := log2(ROW_SIZE);
#     -- INDEX_BITS is the number if bits to
#     -- select a cache line
#     constant INDEX_BITS : natural := log2(NUM_LINES);
#     -- SET_SIZE_BITS is the log base 2 of the set size
#     constant SET_SIZE_BITS : natural := LINE_OFF_BITS
#                                         + INDEX_BITS;
#     -- TAG_BITS is the number of bits of
#     -- the tag part of the address
#     constant TAG_BITS : natural := REAL_ADDR_BITS - SET_SIZE_BITS;
#     -- TAG_WIDTH is the width in bits of each way of the tag RAM
#     constant TAG_WIDTH : natural := TAG_BITS + 7
#                                     - ((TAG_BITS + 7) mod 8);
#     -- WAY_BITS is the number of bits to select a way
#     constant WAY_BITS : natural := log2(NUM_WAYS);
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

#     -- Example of layout for 32 lines of 64 bytes:
#     --
#     -- ..  tag    |index|  line  |
#     -- ..         |   row   |    |
#     -- ..         |     |---|    | ROW_LINEBITS  (3)
#     -- ..         |     |--- - --| LINE_OFF_BITS (6)
#     -- ..         |         |- --| ROW_OFF_BITS  (3)
#     -- ..         |----- ---|    | ROW_BITS      (8)
#     -- ..         |-----|        | INDEX_BITS    (5)
#     -- .. --------|              | TAG_BITS      (45)
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


#     subtype row_t is integer range 0 to BRAM_ROWS-1;
#     subtype index_t is integer range 0 to NUM_LINES-1;
#     subtype way_t is integer range 0 to NUM_WAYS-1;
#     subtype row_in_line_t is unsigned(ROW_LINE_BITS-1 downto 0);
        ROW         = BRAM_ROWS
        INDEX       = NUM_LINES
        WAY         = NUM_WAYS
        ROW_IN_LINE = ROW_LINE_BITS

#     -- The cache data BRAM organized as described above for each way
#     subtype cache_row_t is
#      std_ulogic_vector(wishbone_data_bits-1 downto 0);
        # The cache data BRAM organized as described above for each way
        CACHE_ROW   = WB_DATA_BITS

#     -- The cache tags LUTRAM has a row per set.
#     -- Vivado is a pain and will not handle a
#     -- clean (commented) definition of the cache
#     -- tags as a 3d memory. For now, work around
#     -- it by putting all the tags
#     subtype cache_tag_t is std_logic_vector(TAG_BITS-1 downto 0);
        # The cache tags LUTRAM has a row per set.
        # Vivado is a pain and will not handle a
        # clean (commented) definition of the cache
        # tags as a 3d memory. For now, work around
        # it by putting all the tags
        CACHE_TAG   = TAG_BITS

#     -- type cache_tags_set_t is array(way_t) of cache_tag_t;
#     -- type cache_tags_array_t is array(index_t) of cache_tags_set_t;
#     constant TAG_RAM_WIDTH : natural := TAG_WIDTH * NUM_WAYS;
#     subtype cache_tags_set_t is
#      std_logic_vector(TAG_RAM_WIDTH-1 downto 0);
#     type cache_tags_array_t is array(index_t) of cache_tags_set_t;
        # type cache_tags_set_t is array(way_t) of cache_tag_t;
        # type cache_tags_array_t is array(index_t) of cache_tags_set_t;
        TAG_RAM_WIDTH = TAG_WIDTH * NUM_WAYS

        CACHE_TAG_SET = TAG_RAM_WIDTH

        def CacheTagArray():
            return Array(CacheTagSet() for x in range(INDEX))

#     -- The cache valid bits
#     subtype cache_way_valids_t is
#      std_ulogic_vector(NUM_WAYS-1 downto 0);
#     type cache_valids_t is array(index_t) of cache_way_valids_t;
#     type row_per_line_valid_t is
#      array(0 to ROW_PER_LINE - 1) of std_ulogic;
        # The cache valid bits
        CACHE_WAY_VALID_BITS = NUM_WAYS

        def CacheValidBitsArray():
            return Array(CacheWayValidBits() for x in range(INDEX))

        def RowPerLineValidArray():
            return Array(Signal() for x in range(ROW_PER_LINE))

#     -- Storage. Hopefully "cache_rows" is a BRAM, the rest is LUTs
#     signal cache_tags    : cache_tags_array_t;
#     signal cache_tag_set : cache_tags_set_t;
#     signal cache_valids  : cache_valids_t;
#
#     attribute ram_style : string;
#     attribute ram_style of cache_tags : signal is "distributed";
        # Storage. Hopefully "cache_rows" is a BRAM, the rest is LUTs
        cache_tags       = CacheTagArray()
        cache_tag_set    = Signal(CACHE_TAG_SET)
        cache_valid_bits = CacheValidBitsArray()

        # TODO attribute ram_style : string;
        # TODO attribute ram_style of cache_tags : signal is "distributed";

#     -- L1 TLB.
#     constant TLB_SET_BITS : natural := log2(TLB_SET_SIZE);
#     constant TLB_WAY_BITS : natural := log2(TLB_NUM_WAYS);
#     constant TLB_EA_TAG_BITS : natural :=
#      64 - (TLB_LG_PGSZ + TLB_SET_BITS);
#     constant TLB_TAG_WAY_BITS : natural :=
#      TLB_NUM_WAYS * TLB_EA_TAG_BITS;
#     constant TLB_PTE_BITS : natural := 64;
#     constant TLB_PTE_WAY_BITS : natural :=
#      TLB_NUM_WAYS * TLB_PTE_BITS;
        # L1 TLB
        TLB_SET_BITS     = log2_int(TLB_SET_SIZE)
        TLB_WAY_BITS     = log2_int(TLB_NUM_WAYS)
        TLB_EA_TAG_BITS  = 64 - (TLB_LG_PGSZ + TLB_SET_BITS)
        TLB_TAG_WAY_BITS = TLB_NUM_WAYS * TLB_EA_TAG_BITS
        TLB_PTE_BITS     = 64
        TLB_PTE_WAY_BITS = TLB_NUM_WAYS * TLB_PTE_BITS;

#     subtype tlb_way_t is integer range 0 to TLB_NUM_WAYS - 1;
#     subtype tlb_index_t is integer range 0 to TLB_SET_SIZE - 1;
#     subtype tlb_way_valids_t is
#      std_ulogic_vector(TLB_NUM_WAYS-1 downto 0);
#     type tlb_valids_t is
#      array(tlb_index_t) of tlb_way_valids_t;
#     subtype tlb_tag_t is
#      std_ulogic_vector(TLB_EA_TAG_BITS - 1 downto 0);
#     subtype tlb_way_tags_t is
#      std_ulogic_vector(TLB_TAG_WAY_BITS-1 downto 0);
#     type tlb_tags_t is
#      array(tlb_index_t) of tlb_way_tags_t;
#     subtype tlb_pte_t is
#      std_ulogic_vector(TLB_PTE_BITS - 1 downto 0);
#     subtype tlb_way_ptes_t is
#      std_ulogic_vector(TLB_PTE_WAY_BITS-1 downto 0);
#     type tlb_ptes_t is array(tlb_index_t) of tlb_way_ptes_t;
#     type hit_way_set_t is array(tlb_way_t) of way_t;
        TLB_WAY = TLB_NUM_WAYS

        TLB_INDEX = TLB_SET_SIZE

        TLB_WAY_VALID_BITS = TLB_NUM_WAYS

        def TLBValidBitsArray():
            return Array(
             Signal(TLB_WAY_VALID_BITS) for x in range(TLB_SET_SIZE)
            )

        TLB_TAG = TLB_EA_TAG_BITS

        TLB_WAY_TAGS = TLB_TAG_WAY_BITS

        def TLBTagsArray():
            return Array(
             Signal(TLB_WAY_TAGS) for x in range (TLB_SET_SIZE)
            )

        TLB_PTE = TLB_PTE_BITS

        TLB_WAY_PTES = TLB_PTE_WAY_BITS

        def TLBPtesArray():
            return Array(
             Signal(TLB_WAY_PTES) for x in range(TLB_SET_SIZE)
            )

        def HitWaySet():
            return Array(Signal(WAY) for x in range(TLB_NUM_WAYS))

#     signal dtlb_valids : tlb_valids_t;
#     signal dtlb_tags : tlb_tags_t;
#     signal dtlb_ptes : tlb_ptes_t;

"""note: these are passed to nmigen.hdl.Memory as "attributes".  don't
   know how, just that they are.
"""
#     attribute ram_style of dtlb_tags : signal is "distributed";
#     attribute ram_style of dtlb_ptes : signal is "distributed";
        dtlb_valids = TLBValidBitsArray()
        dtlb_tags   = TLBTagsArray()
        dtlb_ptes   = TLBPtesArray()
        # TODO attribute ram_style of dtlb_tags : signal is "distributed";
        # TODO attribute ram_style of dtlb_ptes : signal is "distributed";


#     -- Record for storing permission, attribute, etc. bits from a PTE
#     type perm_attr_t is record
#         reference : std_ulogic;
#         changed   : std_ulogic;
#         nocache   : std_ulogic;
#         priv      : std_ulogic;
#         rd_perm   : std_ulogic;
#         wr_perm   : std_ulogic;
#     end record;
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

#     function extract_perm_attr(
#      pte : std_ulogic_vector(TLB_PTE_BITS - 1 downto 0))
#      return perm_attr_t is
#         variable pa : perm_attr_t;
#     begin
#         pa.reference := pte(8);
#         pa.changed := pte(7);
#         pa.nocache := pte(5);
#         pa.priv := pte(3);
#         pa.rd_perm := pte(2);
#         pa.wr_perm := pte(1);
#         return pa;
#     end;
        def extract_perm_attr(pte=Signal(TLB_PTE_BITS)):
            pa = PermAttr()
            pa.reference = pte[8]
            pa.changed   = pte[7]
            pa.nocache   = pte[5]
            pa.priv      = pte[3]
            pa.rd_perm   = pte[2]
            pa.wr_perm   = pte[1]
            return pa;

#     constant real_mode_perm_attr : perm_attr_t :=
#      (nocache => '0', others => '1');
        REAL_MODE_PERM_ATTR = PermAttr()
        REAL_MODE_PERM_ATTR.reference = 1
        REAL_MODE_PERM_ATTR.changed   = 1
        REAL_MODE_PERM_ATTR.priv      = 1
        REAL_MODE_PERM_ATTR.rd_perm   = 1
        REAL_MODE_PERM_ATTR.wr_perm   = 1

#     -- Type of operation on a "valid" input
#     type op_t is
#      (
#       OP_NONE,
# 	OP_BAD,        -- NC cache hit, TLB miss, prot/RC failure
#       OP_STCX_FAIL,  -- conditional store w/o reservation
# 	OP_LOAD_HIT,   -- Cache hit on load
# 	OP_LOAD_MISS,  -- Load missing cache
# 	OP_LOAD_NC,    -- Non-cachable load
# 	OP_STORE_HIT,  -- Store hitting cache
# 	OP_STORE_MISS  -- Store missing cache
#      );
        # Type of operation on a "valid" input
        @unique
        class OP(Enum):
          OP_NONE       = 0
          OP_BAD        = 1 # NC cache hit, TLB miss, prot/RC failure
          OP_STCX_FAIL  = 2 # conditional store w/o reservation
          OP_LOAD_HIT   = 3 # Cache hit on load
          OP_LOAD_MISS  = 4 # Load missing cache
          OP_LOAD_NC    = 5 # Non-cachable load
          OP_STORE_HIT  = 6 # Store hitting cache
          OP_STORE_MISS = 7 # Store missing cache

#     -- Cache state machine
#     type state_t is
#      (
#       IDLE,            -- Normal load hit processing
#       RELOAD_WAIT_ACK, -- Cache reload wait ack
#       STORE_WAIT_ACK,  -- Store wait ack
#       NC_LOAD_WAIT_ACK -- Non-cachable load wait ack
#      );
        # Cache state machine
        @unique
        class State(Enum):
            IDLE             = 0 # Normal load hit processing
            RELOAD_WAIT_ACK  = 1 # Cache reload wait ack
            STORE_WAIT_ACK   = 2 # Store wait ack
            NC_LOAD_WAIT_ACK = 3 # Non-cachable load wait ack

#     -- Dcache operations:
#     --
#     -- In order to make timing, we use the BRAMs with
#     -- an output buffer, which means that the BRAM
#     -- output is delayed by an extra cycle.
#     --
#     -- Thus, the dcache has a 2-stage internal pipeline
#     -- for cache hits with no stalls.
#     --
#     -- All other operations are handled via stalling
#     -- in the first stage.
#     --
#     -- The second stage can thus complete a hit at the same
#     -- time as the first stage emits a stall for a complex op.
#
#     -- Stage 0 register, basically contains just the latched request
#     type reg_stage_0_t is record
#         req   : Loadstore1ToDcacheType;
#         tlbie : std_ulogic;
#         doall : std_ulogic;
#         tlbld : std_ulogic;
#         mmu_req : std_ulogic;   -- indicates source of request
#     end record;
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

#     signal r0 : reg_stage_0_t;
#     signal r0_full : std_ulogic;
        r0      = RegStage0()
        r0_full = Signal()

#     type mem_access_request_t is record
#         op        : op_t;
#         valid     : std_ulogic;
#         dcbz      : std_ulogic;
#         real_addr : std_ulogic_vector(REAL_ADDR_BITS - 1 downto 0);
#         data      : std_ulogic_vector(63 downto 0);
#         byte_sel  : std_ulogic_vector(7 downto 0);
#         hit_way   : way_t;
#         same_tag  : std_ulogic;
#         mmu_req   : std_ulogic;
#     end record;
        class MemAccessRequest(RecordObject):
            def __init__(self):
                super().__init__()
                self.op        = Op()
                self.valid     = Signal()
                self.dcbz      = Signal()
                self.real_addr = Signal(REAL_ADDR_BITS)
                self.data      = Signal(64)
                self.byte_sel  = Signal(8)
                self.hit_way   = Signal(WAY)
                self.same_tag  = Signal()
                self.mmu_req   = Signal()

#     -- First stage register, contains state for stage 1 of load hits
#     -- and for the state machine used by all other operations
#     type reg_stage_1_t is record
#         -- Info about the request
#         full    : std_ulogic; -- have uncompleted request
#         mmu_req : std_ulogic; -- request is from MMU
#         req     : mem_access_request_t;
#
#         -- Cache hit state
# 	  hit_way        : way_t;
# 	  hit_load_valid : std_ulogic;
#         hit_index      : index_t;
#         cache_hit      : std_ulogic;
#
#         -- TLB hit state
#         tlb_hit       : std_ulogic;
#         tlb_hit_way   : tlb_way_t;
#         tlb_hit_index : tlb_index_t;
#
# 	  -- 2-stage data buffer for data forwarded from writes to reads
# 	  forward_data1  : std_ulogic_vector(63 downto 0);
# 	  forward_data2  : std_ulogic_vector(63 downto 0);
#         forward_sel1   : std_ulogic_vector(7 downto 0);
# 	  forward_valid1 : std_ulogic;
#         forward_way1   : way_t;
#         forward_row1   : row_t;
#         use_forward1   : std_ulogic;
#         forward_sel    : std_ulogic_vector(7 downto 0);
#
# 	  -- Cache miss state (reload state machine)
#         state            : state_t;
#         dcbz             : std_ulogic;
#         write_bram       : std_ulogic;
#         write_tag        : std_ulogic;
#         slow_valid       : std_ulogic;
#         wb               : wishbone_master_out;
#         reload_tag       : cache_tag_t;
# 	  store_way        : way_t;
# 	  store_row        : row_t;
#         store_index      : index_t;
#         end_row_ix       : row_in_line_t;
#         rows_valid       : row_per_line_valid_t;
#         acks_pending     : unsigned(2 downto 0);
#         inc_acks         : std_ulogic;
#         dec_acks         : std_ulogic;
#
#         -- Signals to complete (possibly with error)
#         ls_valid         : std_ulogic;
#         ls_error         : std_ulogic;
#         mmu_done         : std_ulogic;
#         mmu_error        : std_ulogic;
#         cache_paradox    : std_ulogic;
#
#         -- Signal to complete a failed stcx.
#         stcx_fail        : std_ulogic;
#     end record;
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
                self.hit_way          = Signal(WAY)
                self.hit_load_valid   = Signal()
                self.hit_index        = Signal(INDEX)
                self.cache_hit        = Signal()

                # TLB hit state
                self.tlb_hit          = Signal()
                self.tlb_hit_way      = Signal(TLB_WAY)
                self.tlb_hit_index    = Signal(TLB_SET_SIZE)
                self.
                # 2-stage data buffer for data forwarded from writes to reads
                self.forward_data1    = Signal(64)
                self.forward_data2    = Signal(64)
                self.forward_sel1     = Signal(8)
                self.forward_valid1   = Signal()
                self.forward_way1     = Signal(WAY)
                self.forward_row1     = Signal(ROW)
                self.use_forward1     = Signal()
                self.forward_sel      = Signal(8)

                # Cache miss state (reload state machine)
                self.state            = State()
                self.dcbz             = Signal()
                self.write_bram       = Signal()
                self.write_tag        = Signal()
                self.slow_valid       = Signal()
                self.wb               = WishboneMasterOut()
                self.reload_tag       = Signal(CACHE_TAG)
                self.store_way        = Signal(WAY)
                self.store_row        = Signal(ROW)
                self.store_index      = Signal(INDEX)
                self.end_row_ix       = Signal(ROW_IN_LINE)
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

#     signal r1 : reg_stage_1_t;
        r1 = RegStage1()

#     -- Reservation information
#     --
#     type reservation_t is record
#         valid : std_ulogic;
#         addr  : std_ulogic_vector(63 downto LINE_OFF_BITS);
#     end record;
# Reservation information

        class Reservation(RecordObject):
            def __init__(self):
                super().__init__()
                valid = Signal()
                # TODO LINE_OFF_BITS is 6
                addr  = Signal(63 downto LINE_OFF_BITS)

#     signal reservation : reservation_t;
        reservation = Reservation()

#     -- Async signals on incoming request
#     signal req_index   : index_t;
#     signal req_row     : row_t;
#     signal req_hit_way : way_t;
#     signal req_tag     : cache_tag_t;
#     signal req_op      : op_t;
#     signal req_data    : std_ulogic_vector(63 downto 0);
#     signal req_same_tag : std_ulogic;
#     signal req_go      : std_ulogic;
        # Async signals on incoming request
        req_index    = Signal(INDEX)
        req_row      = Signal(ROW)
        req_hit_way  = Signal(WAY)
        req_tag      = Signal(CACHE_TAG)
        req_op       = Op()
        req_data     = Signal(64)
        req_same_tag = Signal()
        req_go       = Signal()

#     signal early_req_row  : row_t;
#
#     signal cancel_store : std_ulogic;
#     signal set_rsrv     : std_ulogic;
#     signal clear_rsrv   : std_ulogic;
#
#     signal r0_valid   : std_ulogic;
#     signal r0_stall   : std_ulogic;
#
#     signal use_forward1_next : std_ulogic;
#     signal use_forward2_next : std_ulogic;
        early_req_row  = Signal(ROW)

        cancel_store = Signal()
        set_rsrv     = Signal()
        clear_rsrv   = Signal()

        r0_valid   = Signal()
        r0_stall   = Signal()

        use_forward1_next = Signal()
        use_forward2_next = Signal()

#     -- Cache RAM interface
#     type cache_ram_out_t is array(way_t) of cache_row_t;
#     signal cache_out   : cache_ram_out_t;
        # Cache RAM interface
        def CacheRamOut():
            return Array(Signal(CACHE_ROW) for x in range(NUM_WAYS))

        cache_out = CacheRamOut()

#     -- PLRU output interface
#     type plru_out_t is array(index_t) of
#      std_ulogic_vector(WAY_BITS-1 downto 0);
#     signal plru_victim : plru_out_t;
#     signal replace_way : way_t;
        # PLRU output interface
        def PLRUOut():
            return Array(Signal(WAY_BITS) for x in range(Index()))

        plru_victim = PLRUOut()
        replace_way = Signal(WAY)

#     -- Wishbone read/write/cache write formatting signals
#     signal bus_sel     : std_ulogic_vector(7 downto 0);
        # Wishbone read/write/cache write formatting signals
        bus_sel = Signal(8)

#     -- TLB signals
#     signal tlb_tag_way : tlb_way_tags_t;
#     signal tlb_pte_way : tlb_way_ptes_t;
#     signal tlb_valid_way : tlb_way_valids_t;
#     signal tlb_req_index : tlb_index_t;
#     signal tlb_hit : std_ulogic;
#     signal tlb_hit_way : tlb_way_t;
#     signal pte : tlb_pte_t;
#     signal ra : std_ulogic_vector(REAL_ADDR_BITS - 1 downto 0);
#     signal valid_ra : std_ulogic;
#     signal perm_attr : perm_attr_t;
#     signal rc_ok : std_ulogic;
#     signal perm_ok : std_ulogic;
#     signal access_ok : std_ulogic;
        # TLB signals
        tlb_tag_way   = Signal(TLB_WAY_TAGS)
        tlb_pte_way   = Signal(TLB_WAY_PTES)
        tlb_valid_way = Signal(TLB_WAY_VALID_BITS)
        tlb_req_index = Signal(TLB_SET_SIZE)
        tlb_hit       = Signal()
        tlb_hit_way   = Signal(TLB_WAY)
        pte           = Signal(TLB_PTE)
        ra            = Signal(REAL_ADDR_BITS)
        valid_ra      = Signal()
        perm_attr     = PermAttr()
        rc_ok         = Signal()
        perm_ok       = Signal()
        access_ok     = Signal()

#     -- TLB PLRU output interface
#     type tlb_plru_out_t is array(tlb_index_t) of
#      std_ulogic_vector(TLB_WAY_BITS-1 downto 0);
#     signal tlb_plru_victim : tlb_plru_out_t;
        # TLB PLRU output interface
        DEF TLBPLRUOut():
            return Array(Signal(TLB_WAY_BITS) for x in range(TLB_SET_SIZE))

        tlb_plru_victim = TLBPLRUOut()

#     -- Helper functions to decode incoming requests
#
#     -- Return the cache line index (tag index) for an address
#     function get_index(addr: std_ulogic_vector) return index_t is
#     begin
#         return to_integer(
#          unsigned(addr(SET_SIZE_BITS - 1 downto LINE_OFF_BITS))
#         );
#     end;
# Helper functions to decode incoming requests
#
        # Return the cache line index (tag index) for an address
        def get_index(addr):
            return addr[LINE_OFF_BITS:SET_SIZE_BITS]

#     -- Return the cache row index (data memory) for an address
#     function get_row(addr: std_ulogic_vector) return row_t is
#     begin
#         return to_integer(
#          unsigned(addr(SET_SIZE_BITS - 1 downto ROW_OFF_BITS))
#         );
#     end;
        # Return the cache row index (data memory) for an address
        def get_row(addr):
            return addr[ROW_OFF_BITS:SET_SIZE_BITS]

#     -- Return the index of a row within a line
#     function get_row_of_line(row: row_t) return row_in_line_t is
# 	variable row_v : unsigned(ROW_BITS-1 downto 0);
#     begin
# 	row_v := to_unsigned(row, ROW_BITS);
#         return row_v(ROW_LINEBITS-1 downto 0);
#     end;
        # Return the index of a row within a line
        def get_row_of_line(row):
            row_v = Signal(ROW_BITS)
            row_v = Signal(row)
            return row_v[0:ROW_LINE_BITS]

#     -- Returns whether this is the last row of a line
#     function is_last_row_addr(addr: wishbone_addr_type;
#      last: row_in_line_t) return boolean is
#     begin
# 	return
#        unsigned(addr(LINE_OFF_BITS-1 downto ROW_OFF_BITS)) = last;
#     end;
        # Returns whether this is the last row of a line
        def is_last_row_addr(addr, last):
            return addr[ROW_OFF_BITS:LINE_OFF_BITS] == last

#     -- Returns whether this is the last row of a line
#     function is_last_row(row: row_t; last: row_in_line_t)
#      return boolean is
#     begin
#         return get_row_of_line(row) = last;
#     end;
        # Returns whether this is the last row of a line
        def is_last_row(row, last):
            return get_row_of_line(row) == last

#     -- Return the address of the next row in the current cache line
#     function next_row_addr(addr: wishbone_addr_type)
#      return std_ulogic_vector is
# 	variable row_idx : std_ulogic_vector(ROW_LINEBITS-1 downto 0);
# 	variable result  : wishbone_addr_type;
#     begin
# 	-- Is there no simpler way in VHDL to
#       -- generate that 3 bits adder ?
# 	row_idx := addr(LINE_OFF_BITS-1 downto ROW_OFF_BITS);
# 	row_idx := std_ulogic_vector(unsigned(row_idx) + 1);
# 	result := addr;
# 	result(LINE_OFF_BITS-1 downto ROW_OFF_BITS) := row_idx;
# 	return result;
#     end;
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

#     -- Return the next row in the current cache line. We use a
#     -- dedicated function in order to limit the size of the
#     -- generated adder to be only the bits within a cache line
#     -- (3 bits with default settings)
#     function next_row(row: row_t) return row_t is
#        variable row_v  : std_ulogic_vector(ROW_BITS-1 downto 0);
#        variable row_idx : std_ulogic_vector(ROW_LINEBITS-1 downto 0);
#        variable result : std_ulogic_vector(ROW_BITS-1 downto 0);
#     begin
#        row_v := std_ulogic_vector(to_unsigned(row, ROW_BITS));
#        row_idx := row_v(ROW_LINEBITS-1 downto 0);
#        row_v(ROW_LINEBITS-1 downto 0) :=
#         std_ulogic_vector(unsigned(row_idx) + 1);
#        return to_integer(unsigned(row_v));
#     end;
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

#     -- Get the tag value from the address
#     function get_tag(addr: std_ulogic_vector) return cache_tag_t is
#     begin
#         return addr(REAL_ADDR_BITS - 1 downto SET_SIZE_BITS);
#     end;
        # Get the tag value from the address
        def get_tag(addr):
            return addr[SET_SIZE_BITS:REAL_ADDR_BITS]

#     -- Read a tag from a tag memory row
#     function read_tag(way: way_t; tagset: cache_tags_set_t)
#      return cache_tag_t is
#     begin
# 	return tagset(way * TAG_WIDTH + TAG_BITS
#                     - 1 downto way * TAG_WIDTH);
#     end;
        # Read a tag from a tag memory row
        def read_tag(way, tagset):
            return tagset[way *TAG_WIDTH:way * TAG_WIDTH + TAG_BITS]

#     -- Read a TLB tag from a TLB tag memory row
#     function read_tlb_tag(way: tlb_way_t; tags: tlb_way_tags_t)
#      return tlb_tag_t is
#         variable j : integer;
#     begin
#         j := way * TLB_EA_TAG_BITS;
#         return tags(j + TLB_EA_TAG_BITS - 1 downto j);
#     end;
        # Read a TLB tag from a TLB tag memory row
        def read_tlb_tag(way, tags):
            j = Signal()

            j = way * TLB_EA_TAG_BITS
            return tags[j:j + TLB_EA_TAG_BITS]

#     -- Write a TLB tag to a TLB tag memory row
#     procedure write_tlb_tag(way: tlb_way_t; tags: inout tlb_way_tags_t;
#                             tag: tlb_tag_t) is
#         variable j : integer;
#     begin
#         j := way * TLB_EA_TAG_BITS;
#         tags(j + TLB_EA_TAG_BITS - 1 downto j) := tag;
#     end;
        # Write a TLB tag to a TLB tag memory row
        def write_tlb_tag(way, tags), tag):
            j = Signal()

            j = way * TLB_EA_TAG_BITS
            tags[j:j + TLB_EA_TAG_BITS] = tag

#     -- Read a PTE from a TLB PTE memory row
#     function read_tlb_pte(way: tlb_way_t; ptes: tlb_way_ptes_t)
#      return tlb_pte_t is
#         variable j : integer;
#     begin
#         j := way * TLB_PTE_BITS;
#         return ptes(j + TLB_PTE_BITS - 1 downto j);
#     end;
        # Read a PTE from a TLB PTE memory row
        def read_tlb_pte(way, ptes):
            j = Signal()

            j = way * TLB_PTE_BITS
            return ptes[j:j + TLB_PTE_BITS]

#     procedure write_tlb_pte(way: tlb_way_t;
#      ptes: inout tlb_way_ptes_t; newpte: tlb_pte_t) is
#         variable j : integer;
#     begin
#         j := way * TLB_PTE_BITS;
#         ptes(j + TLB_PTE_BITS - 1 downto j) := newpte;
#     end;
        def write_tlb_pte(way, ptes,newpte):
            j = Signal()

            j = way * TLB_PTE_BITS
            return ptes[j:j + TLB_PTE_BITS] = newpte

# begin
#
"""these, because they are constants, can actually be done *as*
   python asserts:
   assert LINE_SIZE % ROWSIZE == 0, "line size not ...."
"""
#     assert LINE_SIZE mod ROW_SIZE = 0
#      report "LINE_SIZE not multiple of ROW_SIZE" severity FAILURE;
#     assert ispow2(LINE_SIZE)
#      report "LINE_SIZE not power of 2" severity FAILURE;
#     assert ispow2(NUM_LINES)
#      report "NUM_LINES not power of 2" severity FAILURE;
#     assert ispow2(ROW_PER_LINE)
#      report "ROW_PER_LINE not power of 2" severity FAILURE;
#     assert (ROW_BITS = INDEX_BITS + ROW_LINEBITS)
#      report "geometry bits don't add up" severity FAILURE;
#     assert (LINE_OFF_BITS = ROW_OFF_BITS + ROW_LINEBITS)
#      report "geometry bits don't add up" severity FAILURE;
#     assert (REAL_ADDR_BITS = TAG_BITS + INDEX_BITS + LINE_OFF_BITS)
#      report "geometry bits don't add up" severity FAILURE;
#     assert (REAL_ADDR_BITS = TAG_BITS + ROW_BITS + ROW_OFF_BITS)
#      report "geometry bits don't add up" severity FAILURE;
#     assert (64 = wishbone_data_bits)
#      report "Can't yet handle a wishbone width that isn't 64-bits"
#      severity FAILURE;
#     assert SET_SIZE_BITS <= TLB_LG_PGSZ
#      report "Set indexed by virtual address" severity FAILURE;
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

#     -- Latch the request in r0.req as long as we're not stalling
#     stage_0 : process(clk)
# Latch the request in r0.req as long as we're not stalling
class Stage0(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()

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
#
#     -- we don't yet handle collisions between loadstore1 requests
#     -- and MMU requests
#     m_out.stall <= '0';
# we don't yet handle collisions between loadstore1 requests
# and MMU requests
comb += m_out.stall.eq(0)

#     -- Hold off the request in r0 when r1 has an uncompleted request
#     r0_stall <= r0_full and r1.full;
#     r0_valid <= r0_full and not r1.full;
#     stall_out <= r0_stall;
# Hold off the request in r0 when r1 has an uncompleted request
comb += r0_stall.eq(r0_full & r1.full)
comb += r0_valid.eq(r0_full & ~r1.full)
comb += stall_out.eq(r0_stall)

#     -- TLB
#     -- Operates in the second cycle on the request latched in r0.req.
#     -- TLB updates write the entry at the end of the second cycle.
#     tlb_read : process(clk)
# TLB
# Operates in the second cycle on the request latched in r0.req.
# TLB updates write the entry at the end of the second cycle.
class TLBRead(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()

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
#             -- If we have any op and the previous op isn't finished,
#             -- then keep the same output for next cycle.
#             if r0_stall = '0' then
# If we have any op and the previous op isn't finished,
# then keep the same output for next cycle.
        with m.If(~r0_stall):
            sync += tlb_valid_way.eq(dtlb_valids[index])
            sync += tlb_tag_way.eq(dtlb_tags[index])
            sync += tlb_pte_way.eq(dtlb_ptes[index])
#             end if;
#         end if;
#     end process;

#     -- Generate TLB PLRUs
#     maybe_tlb_plrus: if TLB_NUM_WAYS > 1 generate
# Generate TLB PLRUs
class MaybeTLBPLRUs(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        with m.If(TLB_NUM_WAYS > 1):
#     begin
# TODO understand how to conver generate statements
# 	tlb_plrus: for i in 0 to TLB_SET_SIZE - 1 generate
# 	    -- TLB PLRU interface
# 	    signal tlb_plru_acc :
#            std_ulogic_vector(TLB_WAY_BITS-1 downto 0);
# 	    signal tlb_plru_acc_en : std_ulogic;
# 	    signal tlb_plru_out :
#            std_ulogic_vector(TLB_WAY_BITS-1 downto 0);
# 	begin
# 	    tlb_plru : entity work.plru
# 		generic map (
# 		    BITS => TLB_WAY_BITS
# 		    )
# 		port map (
# 		    clk => clk,
# 		    rst => rst,
# 		    acc => tlb_plru_acc,
# 		    acc_en => tlb_plru_acc_en,
# 		    lru => tlb_plru_out
# 		    );
#
# 	    process(all)
# 	    begin
# 		-- PLRU interface
# 		if r1.tlb_hit_index = i then
# 		    tlb_plru_acc_en <= r1.tlb_hit;
# 		else
# 		    tlb_plru_acc_en <= '0';
# 		end if;
# 		tlb_plru_acc <=
#                std_ulogic_vector(to_unsigned(
#                                   r1.tlb_hit_way, TLB_WAY_BITS
#                                  ));
# 		tlb_plru_victim(i) <= tlb_plru_out;
# 	    end process;
# 	end generate;
#     end generate;
# end TODO
#
#     tlb_search : process(all)
class TLBSearch(Elaboratable):
    def __init__(self):
        pass

    def elborate(self, platform):
        m = Module()

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
            comb += perm_attr.eq(real_mode_perm_attr)
#         end if;
#     end process;

#     tlb_update : process(clk)
class TLBUpdate(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()

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
                sync += dtlb_valids[i].eq(0)
#             elsif tlbie = '1' then
        with m.Elif(tlbie):
#                 if tlb_hit = '1' then
            with m.If(tlb_hit):
#                     dtlb_valids(tlb_req_index)(tlb_hit_way) <= '0';
                sync += dtlb_valids[tlb_req_index][tlb_hit_way].eq(0)
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
            sync += dtlb_valids[tlb_req_index][repl_way].eq(1)
#             end if;
#         end if;
#     end process;

#     -- Generate PLRUs
#     maybe_plrus: if NUM_WAYS > 1 generate
class MaybePLRUs(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

#     begin
        # TODO learn translation of generate into nmgien @lkcl
# 	plrus: for i in 0 to NUM_LINES-1 generate
# 	    -- PLRU interface
# 	    signal plru_acc    : std_ulogic_vector(WAY_BITS-1 downto 0);
# 	    signal plru_acc_en : std_ulogic;
# 	    signal plru_out    : std_ulogic_vector(WAY_BITS-1 downto 0);
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
#
# 	    process(all)
# 	    begin
# 		-- PLRU interface
# 		if r1.hit_index = i then
# 		    plru_acc_en <= r1.cache_hit;
# 		else
# 		    plru_acc_en <= '0';
# 		end if;
# 		plru_acc <= std_ulogic_vector(to_unsigned(
#                            r1.hit_way, WAY_BITS
#                           ));
# 		plru_victim(i) <= plru_out;
# 	    end process;
# 	end generate;
#     end generate;
#
#     -- Cache tag RAM read port
#     cache_tag_read : process(clk)
#         variable index : index_t;
#     begin
#         if rising_edge(clk) then
#             if r0_stall = '1' then
#                 index := req_index;
#             elsif m_in.valid = '1' then
#                 index := get_index(m_in.addr);
#             else
#                 index := get_index(d_in.addr);
#             end if;
#             cache_tag_set <= cache_tags(index);
#         end if;
#     end process;
#
#     -- Cache request parsing and hit detection
#     dcache_request : process(all)
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
#         variable rel_match   : std_ulogic;
#     begin
# 	  -- Extract line, row and tag from request
#         req_index <= get_index(r0.req.addr);
#         req_row <= get_row(r0.req.addr);
#         req_tag <= get_tag(ra);
#
#         go := r0_valid and not (r0.tlbie or r0.tlbld)
#               and not r1.ls_error;
#
# 	  -- Test if pending request is a hit on any way
#         -- In order to make timing in virtual mode,
#         -- when we are using the TLB, we compare each
#         --way with each of the real addresses from each way of
#         -- the TLB, and then decide later which match to use.
#         hit_way := 0;
#         is_hit := '0';
#         rel_match := '0';
#         if r0.req.virt_mode = '1' then
#             rel_matches := (others => '0');
#             for j in tlb_way_t loop
#                 hit_way_set(j) := 0;
#                 s_hit := '0';
#                 s_pte := read_tlb_pte(j, tlb_pte_way);
#                 s_ra :=
#                  s_pte(REAL_ADDR_BITS - 1 downto TLB_LG_PGSZ)
#                  & r0.req.addr(TLB_LG_PGSZ - 1 downto 0);
#                 s_tag := get_tag(s_ra);
#                 for i in way_t loop
#                     if go = '1' and cache_valids(req_index)(i) = '1'
#                      and read_tag(i, cache_tag_set) = s_tag
#                      and tlb_valid_way(j) = '1' then
#                         hit_way_set(j) := i;
#                         s_hit := '1';
#                     end if;
#                 end loop;
#                 hit_set(j) := s_hit;
#                 if s_tag = r1.reload_tag then
#                     rel_matches(j) := '1';
#                 end if;
#             end loop;
#             if tlb_hit = '1' then
#                 is_hit := hit_set(tlb_hit_way);
#                 hit_way := hit_way_set(tlb_hit_way);
#                 rel_match := rel_matches(tlb_hit_way);
#             end if;
#         else
#             s_tag := get_tag(r0.req.addr);
#             for i in way_t loop
#                 if go = '1' and cache_valids(req_index)(i) = '1' and
#                     read_tag(i, cache_tag_set) = s_tag then
#                     hit_way := i;
#                     is_hit := '1';
#                 end if;
#             end loop;
#             if s_tag = r1.reload_tag then
#                 rel_match := '1';
#             end if;
#         end if;
#         req_same_tag <= rel_match;
#
#         -- See if the request matches the line currently being reloaded
#         if r1.state = RELOAD_WAIT_ACK and req_index = r1.store_index
#          and rel_match = '1' then
#             -- For a store, consider this a hit even if the row isn't
#             -- valid since it will be by the time we perform the store.
#             -- For a load, check the appropriate row valid bit.
#             is_hit :=
#              not r0.req.load or r1.rows_valid(req_row mod ROW_PER_LINE);
#             hit_way := replace_way;
#         end if;
#
#         -- Whether to use forwarded data for a load or not
#         use_forward1_next <= '0';
#         if get_row(r1.req.real_addr) = req_row
#          and r1.req.hit_way = hit_way then
#             -- Only need to consider r1.write_bram here, since if we
#             -- are writing refill data here, then we don't have a
#             -- cache hit this cycle on the line being refilled.
#             -- (There is the possibility that the load following the
#             -- load miss that started the refill could be to the old
#             -- contents of the victim line, since it is a couple of
#             -- cycles after the refill starts before we see the updated
#             -- cache tag. In that case we don't use the bypass.)
#             use_forward1_next <= r1.write_bram;
#         end if;
#         use_forward2_next <= '0';
#         if r1.forward_row1 = req_row and r1.forward_way1 = hit_way then
#             use_forward2_next <= r1.forward_valid1;
#         end if;
#
# 	-- The way that matched on a hit
# 	req_hit_way <= hit_way;
#
#         -- The way to replace on a miss
#         if r1.write_tag = '1' then
#             replace_way <= to_integer(unsigned(
#                             plru_victim(r1.store_index)
#                            ));
#         else
#             replace_way <= r1.store_way;
#         end if;
#
#         -- work out whether we have permission for this access
#         -- NB we don't yet implement AMR, thus no KUAP
#         rc_ok <= perm_attr.reference and
#                  (r0.req.load or perm_attr.changed);
#         perm_ok <= (r0.req.priv_mode or not perm_attr.priv) and
#                    (perm_attr.wr_perm or (r0.req.load
#                    and perm_attr.rd_perm));
#         access_ok <= valid_ra and perm_ok and rc_ok;
#
# 	-- Combine the request and cache hit status to decide what
# 	-- operation needs to be done
# 	--
#         nc := r0.req.nc or perm_attr.nocache;
#         op := OP_NONE;
#         if go = '1' then
#             if access_ok = '0' then
#                 op := OP_BAD;
#             elsif cancel_store = '1' then
#                 op := OP_STCX_FAIL;
#             else
#                 opsel := r0.req.load & nc & is_hit;
#                 case opsel is
#                     when "101" => op := OP_LOAD_HIT;
#                     when "100" => op := OP_LOAD_MISS;
#                     when "110" => op := OP_LOAD_NC;
#                     when "001" => op := OP_STORE_HIT;
#                     when "000" => op := OP_STORE_MISS;
#                     when "010" => op := OP_STORE_MISS;
#                     when "011" => op := OP_BAD;
#                     when "111" => op := OP_BAD;
#                     when others => op := OP_NONE;
#                 end case;
#             end if;
#         end if;
# 	req_op <= op;
#         req_go <= go;
#
#         -- Version of the row number that is valid one cycle earlier
#         -- in the cases where we need to read the cache data BRAM.
#         -- If we're stalling then we need to keep reading the last
#         -- row requested.
#         if r0_stall = '0' then
#             if m_in.valid = '1' then
#                 early_req_row <= get_row(m_in.addr);
#             else
#                 early_req_row <= get_row(d_in.addr);
#             end if;
#         else
#             early_req_row <= req_row;
#         end if;
#     end process;
#
#     -- Wire up wishbone request latch out of stage 1
#     wishbone_out <= r1.wb;
#
#     -- Handle load-with-reservation and store-conditional instructions
#     reservation_comb: process(all)
#     begin
#         cancel_store <= '0';
#         set_rsrv <= '0';
#         clear_rsrv <= '0';
#         if r0_valid = '1' and r0.req.reserve = '1' then
#             -- XXX generate alignment interrupt if address
#             -- is not aligned XXX or if r0.req.nc = '1'
#             if r0.req.load = '1' then
#                 -- load with reservation
#                 set_rsrv <= '1';
#             else
#                 -- store conditional
#                 clear_rsrv <= '1';
#                 if reservation.valid = '0' or r0.req.addr(63
#                  downto LINE_OFF_BITS) /= reservation.addr then
#                     cancel_store <= '1';
#                 end if;
#             end if;
#         end if;
#     end process;
#
#     reservation_reg: process(clk)
#     begin
#         if rising_edge(clk) then
#             if rst = '1' then
#                 reservation.valid <= '0';
#             elsif r0_valid = '1' and access_ok = '1' then
#                 if clear_rsrv = '1' then
#                     reservation.valid <= '0';
#                 elsif set_rsrv = '1' then
#                     reservation.valid <= '1';
#                     reservation.addr <=
#                      r0.req.addr(63 downto LINE_OFF_BITS);
#                 end if;
#             end if;
#         end if;
#     end process;
#
#     -- Return data for loads & completion control logic
#     --
#     writeback_control: process(all)
#         variable data_out : std_ulogic_vector(63 downto 0);
#         variable data_fwd : std_ulogic_vector(63 downto 0);
#         variable j        : integer;
#     begin
#         -- Use the bypass if are reading the row that was
#         -- written 1 or 2 cycles ago, including for the
#         -- slow_valid = 1 case (i.e. completing a load
#         -- miss or a non-cacheable load).
#         if r1.use_forward1 = '1' then
#             data_fwd := r1.forward_data1;
#         else
#             data_fwd := r1.forward_data2;
#         end if;
#         data_out := cache_out(r1.hit_way);
#         for i in 0 to 7 loop
#             j := i * 8;
#             if r1.forward_sel(i) = '1' then
#                 data_out(j + 7 downto j) := data_fwd(j + 7 downto j);
#             end if;
#         end loop;
#
# 	  d_out.valid <= r1.ls_valid;
# 	  d_out.data <= data_out;
#         d_out.store_done <= not r1.stcx_fail;
#         d_out.error <= r1.ls_error;
#         d_out.cache_paradox <= r1.cache_paradox;
#
#         -- Outputs to MMU
#         m_out.done <= r1.mmu_done;
#         m_out.err <= r1.mmu_error;
#         m_out.data <= data_out;
#
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
#
#         if r1.mmu_req = '0' then
#             -- Request came from loadstore1...
#             -- Load hit case is the standard path
#             if r1.hit_load_valid = '1' then
#                 report
#                  "completing load hit data=" & to_hstring(data_out);
#             end if;
#
#             -- error cases complete without stalling
#             if r1.ls_error = '1' then
#                 report "completing ld/st with error";
#             end if;
#
#             -- Slow ops (load miss, NC, stores)
#             if r1.slow_valid = '1' then
#                 report
#                  "completing store or load miss data="
#                   & to_hstring(data_out);
#             end if;
#
#         else
#             -- Request came from MMU
#             if r1.hit_load_valid = '1' then
#                 report "completing load hit to MMU, data="
#                  & to_hstring(m_out.data);
#             end if;
#
#             -- error cases complete without stalling
#             if r1.mmu_error = '1' then
#                 report "completing MMU ld with error";
#             end if;
#
#             -- Slow ops (i.e. load miss)
#             if r1.slow_valid = '1' then
#                 report "completing MMU load miss, data="
#                  & to_hstring(m_out.data);
#             end if;
#         end if;
#
#     end process;
#
#
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
# 	signal do_read  : std_ulogic;
# 	signal rd_addr  : std_ulogic_vector(ROW_BITS-1 downto 0);
# 	signal do_write : std_ulogic;
# 	signal wr_addr  : std_ulogic_vector(ROW_BITS-1 downto 0);
# 	signal wr_data  :
#        std_ulogic_vector(wishbone_data_bits-1 downto 0);
# 	signal wr_sel   : std_ulogic_vector(ROW_SIZE-1 downto 0);
# 	signal wr_sel_m : std_ulogic_vector(ROW_SIZE-1 downto 0);
# 	signal dout     : cache_row_t;
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
# 	begin
# 	    -- Cache hit reads
# 	    do_read <= '1';
# 	    rd_addr <=
#            std_ulogic_vector(to_unsigned(early_req_row, ROW_BITS));
# 	    cache_out(i) <= dout;
#
# 	    -- Write mux:
# 	    --
# 	    -- Defaults to wishbone read responses (cache refill)
# 	    --
# 	    -- For timing, the mux on wr_data/sel/addr is not
#           -- dependent on anything other than the current state.
#           wr_sel_m <= (others => '0');
#
# 	    do_write <= '0';
#             if r1.write_bram = '1' then
#                 -- Write store data to BRAM.  This happens one
#                 -- cycle after the store is in r0.
#                 wr_data <= r1.req.data;
#                 wr_sel  <= r1.req.byte_sel;
#                 wr_addr <= std_ulogic_vector(to_unsigned(
#                             get_row(r1.req.real_addr), ROW_BITS
#                            ));
#                 if i = r1.req.hit_way then
#                     do_write <= '1';
#                 end if;
# 	    else
# 		-- Otherwise, we might be doing a reload or a DCBZ
#                 if r1.dcbz = '1' then
#                     wr_data <= (others => '0');
#                 else
#                     wr_data <= wishbone_in.dat;
#                 end if;
#                 wr_addr <= std_ulogic_vector(to_unsigned(
#                             r1.store_row, ROW_BITS
#                            ));
#                 wr_sel <= (others => '1');
#
#                 if r1.state = RELOAD_WAIT_ACK and
#                 wishbone_in.ack = '1' and replace_way = i then
#                     do_write <= '1';
#                 end if;
# 	    end if;
#
#             -- Mask write selects with do_write since BRAM
#             -- doesn't have a global write-enable
#             if do_write = '1' then
#                 wr_sel_m <= wr_sel;
#             end if;
#
#         end process;
#     end generate;
#
#     -- Cache hit synchronous machine for the easy case.
#     -- This handles load hits.
#     -- It also handles error cases (TLB miss, cache paradox)
#     dcache_fast_hit : process(clk)
#     begin
#         if rising_edge(clk) then
#             if req_op /= OP_NONE then
# 		report "op:" & op_t'image(req_op) &
# 		    " addr:" & to_hstring(r0.req.addr) &
# 		    " nc:" & std_ulogic'image(r0.req.nc) &
# 		    " idx:" & integer'image(req_index) &
# 		    " tag:" & to_hstring(req_tag) &
# 		    " way: " & integer'image(req_hit_way);
# 	      end if;
#             if r0_valid = '1' then
#                 r1.mmu_req <= r0.mmu_req;
#             end if;
#
#             -- Fast path for load/store hits.
#             -- Set signals for the writeback controls.
#             r1.hit_way <= req_hit_way;
#             r1.hit_index <= req_index;
# 	      if req_op = OP_LOAD_HIT then
# 	          r1.hit_load_valid <= '1';
# 	      else
# 		  r1.hit_load_valid <= '0';
# 	      end if;
#             if req_op = OP_LOAD_HIT or req_op = OP_STORE_HIT then
#                 r1.cache_hit <= '1';
#             else
#                 r1.cache_hit <= '0';
#             end if;
#
#             if req_op = OP_BAD then
#                 report "Signalling ld/st error valid_ra=" &
#                  std_ulogic'image(valid_ra) & " rc_ok=" &
#                  std_ulogic'image(rc_ok) & " perm_ok=" &
#                  std_ulogic'image(perm_ok);
#                 r1.ls_error <= not r0.mmu_req;
#                 r1.mmu_error <= r0.mmu_req;
#                 r1.cache_paradox <= access_ok;
#             else
#                 r1.ls_error <= '0';
#                 r1.mmu_error <= '0';
#                 r1.cache_paradox <= '0';
#             end if;
#
#             if req_op = OP_STCX_FAIL then
#                 r1.stcx_fail <= '1';
#             else
#                 r1.stcx_fail <= '0';
#             end if;
#
#             -- Record TLB hit information for updating TLB PLRU
#             r1.tlb_hit <= tlb_hit;
#             r1.tlb_hit_way <= tlb_hit_way;
#             r1.tlb_hit_index <= tlb_req_index;
#
# 	  end if;
#     end process;
#
#     -- Memory accesses are handled by this state machine:
#     --
#     --   * Cache load miss/reload (in conjunction with "rams")
#     --   * Load hits for non-cachable forms
#     --   * Stores (the collision case is handled in "rams")
#     --
#     -- All wishbone requests generation is done here.
#     -- This machine operates at stage 1.
#     dcache_slow : process(clk)
# 	  variable stbs_done : boolean;
#         variable req       : mem_access_request_t;
#         variable acks      : unsigned(2 downto 0);
#     begin
#         if rising_edge(clk) then
#             r1.use_forward1 <= use_forward1_next;
#             r1.forward_sel <= (others => '0');
#             if use_forward1_next = '1' then
#                 r1.forward_sel <= r1.req.byte_sel;
#             elsif use_forward2_next = '1' then
#                 r1.forward_sel <= r1.forward_sel1;
#             end if;
#
#             r1.forward_data2 <= r1.forward_data1;
#             if r1.write_bram = '1' then
#                 r1.forward_data1 <= r1.req.data;
#                 r1.forward_sel1 <= r1.req.byte_sel;
#                 r1.forward_way1 <= r1.req.hit_way;
#                 r1.forward_row1 <= get_row(r1.req.real_addr);
#                 r1.forward_valid1 <= '1';
#             else
#                 if r1.dcbz = '1' then
#                     r1.forward_data1 <= (others => '0');
#                 else
#                     r1.forward_data1 <= wishbone_in.dat;
#                 end if;
#                 r1.forward_sel1 <= (others => '1');
#                 r1.forward_way1 <= replace_way;
#                 r1.forward_row1 <= r1.store_row;
#                 r1.forward_valid1 <= '0';
#             end if;
#
# 	    -- On reset, clear all valid bits to force misses
#             if rst = '1' then
# 		for i in index_t loop
# 		    cache_valids(i) <= (others => '0');
# 		end loop;
#                 r1.state <= IDLE;
#                 r1.full <= '0';
# 		r1.slow_valid <= '0';
#                 r1.wb.cyc <= '0';
#                 r1.wb.stb <= '0';
#                 r1.ls_valid <= '0';
#                 r1.mmu_done <= '0';
#
# 		-- Not useful normally but helps avoiding
#               -- tons of sim warnings
# 		r1.wb.adr <= (others => '0');
#             else
# 		-- One cycle pulses reset
# 		r1.slow_valid <= '0';
#                 r1.write_bram <= '0';
#                 r1.inc_acks <= '0';
#                 r1.dec_acks <= '0';
#
#                 r1.ls_valid <= '0';
#                 -- complete tlbies and TLB loads in the third cycle
#                 r1.mmu_done <= r0_valid and (r0.tlbie or r0.tlbld);
#                 if req_op = OP_LOAD_HIT or req_op = OP_STCX_FAIL then
#                     if r0.mmu_req = '0' then
#                         r1.ls_valid <= '1';
#                     else
#                         r1.mmu_done <= '1';
#                     end if;
#                 end if;
#
#                 if r1.write_tag = '1' then
#                     -- Store new tag in selected way
#                     for i in 0 to NUM_WAYS-1 loop
#                         if i = replace_way then
#                             cache_tags(r1.store_index)(
#                              (i + 1) * TAG_WIDTH - 1
#                              downto i * TAG_WIDTH
#                             ) <=
#                              (TAG_WIDTH - 1 downto TAG_BITS => '0')
#                              & r1.reload_tag;
#                         end if;
#                     end loop;
#                     r1.store_way <= replace_way;
#                     r1.write_tag <= '0';
#                 end if;
#
#                 -- Take request from r1.req if there is one there,
#                 -- else from req_op, ra, etc.
#                 if r1.full = '1' then
#                     req := r1.req;
#                 else
#                     req.op := req_op;
#                     req.valid := req_go;
#                     req.mmu_req := r0.mmu_req;
#                     req.dcbz := r0.req.dcbz;
#                     req.real_addr := ra;
#                     -- Force data to 0 for dcbz
#                     if r0.req.dcbz = '0' then
#                         req.data := r0.req.data;
#                     else
#                         req.data := (others => '0');
#                     end if;
#                     -- Select all bytes for dcbz
#                     -- and for cacheable loads
#                     if r0.req.dcbz = '1'
#                      or (r0.req.load = '1' and r0.req.nc = '0') then
#                         req.byte_sel := (others => '1');
#                     else
#                         req.byte_sel := r0.req.byte_sel;
#                     end if;
#                     req.hit_way := req_hit_way;
#                     req.same_tag := req_same_tag;
#
#                     -- Store the incoming request from r0,
#                     -- if it is a slow request
#                     -- Note that r1.full = 1 implies req_op = OP_NONE
#                     if req_op = OP_LOAD_MISS or req_op = OP_LOAD_NC
#                      or req_op = OP_STORE_MISS
#                      or req_op = OP_STORE_HIT then
#                         r1.req <= req;
#                         r1.full <= '1';
#                     end if;
#                 end if;
#
# 		-- Main state machine
# 		case r1.state is
#                 when IDLE =>
#                     r1.wb.adr <= req.real_addr(r1.wb.adr'left downto 0);
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
#
#                     if req.op = OP_STORE_HIT then
#                         r1.store_way <= req.hit_way;
#                     end if;
#
#                     -- Reset per-row valid bits,
#                     -- ready for handling OP_LOAD_MISS
#                     for i in 0 to ROW_PER_LINE - 1 loop
#                         r1.rows_valid(i) <= '0';
#                     end loop;
#
#                     case req.op is
#                     when OP_LOAD_HIT =>
#                         -- stay in IDLE state
#
#                     when OP_LOAD_MISS =>
# 			-- Normal load cache miss,
#                       -- start the reload machine
# 			report "cache miss real addr:" &
#                        to_hstring(req.real_addr) & " idx:" &
#                        integer'image(get_index(req.real_addr)) &
# 			 " tag:" & to_hstring(get_tag(req.real_addr));
#
# 			-- Start the wishbone cycle
# 			r1.wb.we  <= '0';
# 			r1.wb.cyc <= '1';
# 			r1.wb.stb <= '1';
#
# 			-- Track that we had one request sent
# 			r1.state <= RELOAD_WAIT_ACK;
#                         r1.write_tag <= '1';
#
# 		    when OP_LOAD_NC =>
#                         r1.wb.cyc <= '1';
#                         r1.wb.stb <= '1';
# 			r1.wb.we <= '0';
# 			r1.state <= NC_LOAD_WAIT_ACK;
#
#                     when OP_STORE_HIT | OP_STORE_MISS =>
#                         if req.dcbz = '0' then
#                             r1.state <= STORE_WAIT_ACK;
#                             r1.acks_pending <= to_unsigned(1, 3);
#                             r1.full <= '0';
#                             r1.slow_valid <= '1';
#                             if req.mmu_req = '0' then
#                                 r1.ls_valid <= '1';
#                             else
#                                 r1.mmu_done <= '1';
#                             end if;
#                             if req.op = OP_STORE_HIT then
#                                 r1.write_bram <= '1';
#                             end if;
#                         else
#                             -- dcbz is handled much like a load
#                             -- miss except that we are writing
#                             -- to memory instead of reading
#                             r1.state <= RELOAD_WAIT_ACK;
#                             if req.op = OP_STORE_MISS then
#                                 r1.write_tag <= '1';
#                             end if;
#                         end if;
#                         r1.wb.we <= '1';
#                         r1.wb.cyc <= '1';
#                         r1.wb.stb <= '1';
#
# 		    -- OP_NONE and OP_BAD do nothing
#                   -- OP_BAD & OP_STCX_FAIL were handled above already
# 		    when OP_NONE =>
#                     when OP_BAD =>
#                     when OP_STCX_FAIL =>
# 		    end case;
#
#                 when RELOAD_WAIT_ACK =>
#                     -- Requests are all sent if stb is 0
# 		    stbs_done := r1.wb.stb = '0';
#
# 		    -- If we are still sending requests,
#                   -- was one accepted?
# 		    if wishbone_in.stall = '0' and not stbs_done then
# 			-- That was the last word ? We are done sending.
#                       -- Clear stb and set stbs_done so we can handle
#                       -- an eventual last ack on the same cycle.
# 			if is_last_row_addr(r1.wb.adr, r1.end_row_ix) then
# 			    r1.wb.stb <= '0';
# 			    stbs_done := true;
# 			end if;
#
# 			-- Calculate the next row address
# 			r1.wb.adr <= next_row_addr(r1.wb.adr);
# 		    end if;
#
# 		    -- Incoming acks processing
#                     r1.forward_valid1 <= wishbone_in.ack;
# 		    if wishbone_in.ack = '1' then
#                         r1.rows_valid(
#                          r1.store_row mod ROW_PER_LINE
#                         ) <= '1';
#                         -- If this is the data we were looking for,
#                         -- we can complete the request next cycle.
#                         -- Compare the whole address in case the
#                         -- request in r1.req is not the one that
#                         -- started this refill.
# 			if r1.full = '1' and r1.req.same_tag = '1'
#                        and ((r1.dcbz = '1' and r1.req.dcbz = '1')
#                        or (r1.dcbz = '0' and r1.req.op = OP_LOAD_MISS))
#                        and r1.store_row = get_row(r1.req.real_addr) then
#                             r1.full <= '0';
#                             r1.slow_valid <= '1';
#                             if r1.mmu_req = '0' then
#                                 r1.ls_valid <= '1';
#                             else
#                                 r1.mmu_done <= '1';
#                             end if;
#                             r1.forward_sel <= (others => '1');
#                             r1.use_forward1 <= '1';
# 			end if;
#
# 			-- Check for completion
# 			if stbs_done and is_last_row(r1.store_row,
#                        r1.end_row_ix) then
# 			    -- Complete wishbone cycle
# 			    r1.wb.cyc <= '0';
#
# 			    -- Cache line is now valid
# 			    cache_valids(r1.store_index)(
#                            r1.store_way
#                           ) <= '1';
#
#                           r1.state <= IDLE;
# 			end if;
#
# 			-- Increment store row counter
# 			r1.store_row <= next_row(r1.store_row);
# 		    end if;
#
#                 when STORE_WAIT_ACK =>
# 		    stbs_done := r1.wb.stb = '0';
#                     acks := r1.acks_pending;
#                     if r1.inc_acks /= r1.dec_acks then
#                         if r1.inc_acks = '1' then
#                             acks := acks + 1;
#                         else
#                             acks := acks - 1;
#                         end if;
#                     end if;
#                     r1.acks_pending <= acks;
# 		      -- Clear stb when slave accepted request
#                     if wishbone_in.stall = '0' then
#                         -- See if there is another store waiting
#                         -- to be done which is in the same real page.
#                         if req.valid = '1' then
#                             r1.wb.adr(
#                              SET_SIZE_BITS - 1 downto 0
#                             ) <= req.real_addr(
#                              SET_SIZE_BITS - 1 downto 0
#                             );
#                             r1.wb.dat <= req.data;
#                             r1.wb.sel <= req.byte_sel;
#                         end if;
#                         if acks < 7 and req.same_tag = '1'
#                          and (req.op = OP_STORE_MISS
#                          or req.op = OP_STORE_HIT) then
#                             r1.wb.stb <= '1';
#                             stbs_done := false;
#                             if req.op = OP_STORE_HIT then
#                                 r1.write_bram <= '1';
#                             end if;
#                             r1.full <= '0';
#                             r1.slow_valid <= '1';
#                             -- Store requests never come from the MMU
#                             r1.ls_valid <= '1';
#                             stbs_done := false;
#                             r1.inc_acks <= '1';
#                         else
#                             r1.wb.stb <= '0';
#                             stbs_done := true;
#                         end if;
# 		    end if;
#
# 		    -- Got ack ? See if complete.
# 		    if wishbone_in.ack = '1' then
#                         if stbs_done and acks = 1 then
#                             r1.state <= IDLE;
#                             r1.wb.cyc <= '0';
#                             r1.wb.stb <= '0';
#                         end if;
#                         r1.dec_acks <= '1';
# 		    end if;
#
#                 when NC_LOAD_WAIT_ACK =>
# 		    -- Clear stb when slave accepted request
#                     if wishbone_in.stall = '0' then
# 			r1.wb.stb <= '0';
# 		    end if;
#
# 		    -- Got ack ? complete.
# 		    if wishbone_in.ack = '1' then
#                         r1.state <= IDLE;
#                         r1.full <= '0';
# 			r1.slow_valid <= '1';
#                         if r1.mmu_req = '0' then
#                             r1.ls_valid <= '1';
#                         else
#                             r1.mmu_done <= '1';
#                         end if;
#                         r1.forward_sel <= (others => '1');
#                         r1.use_forward1 <= '1';
# 			r1.wb.cyc <= '0';
# 			r1.wb.stb <= '0';
# 		    end if;
#                 end case;
# 	    end if;
# 	end if;
#     end process;
#
#     dc_log: if LOG_LENGTH > 0 generate
#         signal log_data : std_ulogic_vector(19 downto 0);
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
#             end if;
#         end process;
#         log_out <= log_data;
#     end generate;
# end;
