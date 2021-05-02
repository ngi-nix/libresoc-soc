"""DCache

based on Anton Blanchard microwatt dcache.vhdl

note that the microwatt dcache wishbone interface expects "stall".
for simplicity at the moment this is hard-coded to cyc & ~ack.
see WB4 spec, p84, section 5.2.1

IMPORTANT: for store, the data is sampled the cycle AFTER the "valid"
is raised.  sigh
"""

import sys

from nmutil.gtkw import write_gtkw

sys.setrecursionlimit(1000000)

from enum import Enum, unique

from nmigen import Module, Signal, Elaboratable, Cat, Repl, Array, Const
from nmutil.util import Display

from copy import deepcopy
from random import randint, seed

from nmigen.cli import main
from nmutil.iocontrol import RecordObject
from nmigen.utils import log2_int
from soc.experiment.mem_types import (LoadStore1ToDCacheType,
                                     DCacheToLoadStore1Type,
                                     MMUToDCacheType,
                                     DCacheToMMUType)

from soc.experiment.wb_types import (WB_ADDR_BITS, WB_DATA_BITS, WB_SEL_BITS,
                                WBAddrType, WBDataType, WBSelType,
                                WBMasterOut, WBSlaveOut,
                                WBMasterOutVector, WBSlaveOutVector,
                                WBIOMasterOut, WBIOSlaveOut)

from soc.experiment.cache_ram import CacheRam
#from soc.experiment.plru import PLRU
from nmutil.plru import PLRU

# for test
from soc.bus.sram import SRAM
from nmigen import Memory
from nmigen.cli import rtlil

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator

from nmutil.util import wrap


# TODO: make these parameters of DCache at some point
LINE_SIZE = 64    # Line size in bytes
NUM_LINES = 16    # Number of lines in a set
NUM_WAYS = 4      # Number of ways
TLB_SET_SIZE = 64 # L1 DTLB entries per set
TLB_NUM_WAYS = 2  # L1 DTLB number of sets
TLB_LG_PGSZ = 12  # L1 DTLB log_2(page_size)
LOG_LENGTH = 0    # Non-zero to enable log data collection

# BRAM organisation: We never access more than
#     -- WB_DATA_BITS at a time so to save
#     -- resources we make the array only that wide, and
#     -- use consecutive indices for to make a cache "line"
#     --
#     -- ROW_SIZE is the width in bytes of the BRAM
#     -- (based on WB, so 64-bits)
ROW_SIZE = WB_DATA_BITS // 8;

# ROW_PER_LINE is the number of row (wishbone
# transactions) in a line
ROW_PER_LINE = LINE_SIZE // ROW_SIZE

# BRAM_ROWS is the number of rows in BRAM needed
# to represent the full dcache
BRAM_ROWS = NUM_LINES * ROW_PER_LINE

print ("ROW_SIZE", ROW_SIZE)
print ("ROW_PER_LINE", ROW_PER_LINE)
print ("BRAM_ROWS", BRAM_ROWS)
print ("NUM_WAYS", NUM_WAYS)

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
layout = """\
  ..  tag    |index|  line  |
  ..         |   row   |    |
  ..         |     |---|    | ROW_LINE_BITS  (3)
  ..         |     |--- - --| LINE_OFF_BITS (6)
  ..         |         |- --| ROW_OFF_BITS  (3)
  ..         |----- ---|    | ROW_BITS      (8)
  ..         |-----|        | INDEX_BITS    (5)
  .. --------|              | TAG_BITS      (45)
"""
print (layout)
print ("Dcache TAG %d IDX %d ROW_BITS %d ROFF %d LOFF %d RLB %d" % \
            (TAG_BITS, INDEX_BITS, ROW_BITS,
             ROW_OFF_BITS, LINE_OFF_BITS, ROW_LINE_BITS))
print ("index @: %d-%d" % (LINE_OFF_BITS, SET_SIZE_BITS))
print ("row @: %d-%d" % (LINE_OFF_BITS, ROW_OFF_BITS))
print ("tag @: %d-%d width %d" % (SET_SIZE_BITS, REAL_ADDR_BITS, TAG_WIDTH))

TAG_RAM_WIDTH = TAG_WIDTH * NUM_WAYS

print ("TAG_RAM_WIDTH", TAG_RAM_WIDTH)

def CacheTagArray():
    return Array(Signal(TAG_RAM_WIDTH, name="cachetag_%d" % x) \
                        for x in range(NUM_LINES))

def CacheValidBitsArray():
    return Array(Signal(NUM_WAYS, name="cachevalid_%d" % x) \
                        for x in range(NUM_LINES))

def RowPerLineValidArray():
    return Array(Signal(name="rows_valid%d" % x) \
                        for x in range(ROW_PER_LINE))

# L1 TLB
TLB_SET_BITS     = log2_int(TLB_SET_SIZE)
TLB_WAY_BITS     = log2_int(TLB_NUM_WAYS)
TLB_EA_TAG_BITS  = 64 - (TLB_LG_PGSZ + TLB_SET_BITS)
TLB_TAG_WAY_BITS = TLB_NUM_WAYS * TLB_EA_TAG_BITS
TLB_PTE_BITS     = 64
TLB_PTE_WAY_BITS = TLB_NUM_WAYS * TLB_PTE_BITS;

def ispow2(x):
    return (1<<log2_int(x, False)) == x

assert (LINE_SIZE % ROW_SIZE) == 0, "LINE_SIZE not multiple of ROW_SIZE"
assert ispow2(LINE_SIZE), "LINE_SIZE not power of 2"
assert ispow2(NUM_LINES), "NUM_LINES not power of 2"
assert ispow2(ROW_PER_LINE), "ROW_PER_LINE not power of 2"
assert ROW_BITS == (INDEX_BITS + ROW_LINE_BITS), "geometry bits don't add up"
assert (LINE_OFF_BITS == ROW_OFF_BITS + ROW_LINE_BITS), \
        "geometry bits don't add up"
assert REAL_ADDR_BITS == (TAG_BITS + INDEX_BITS + LINE_OFF_BITS), \
        "geometry bits don't add up"
assert REAL_ADDR_BITS == (TAG_BITS + ROW_BITS + ROW_OFF_BITS), \
         "geometry bits don't add up"
assert 64 == WB_DATA_BITS, "Can't yet handle wb width that isn't 64-bits"
assert SET_SIZE_BITS <= TLB_LG_PGSZ, "Set indexed by virtual address"


def TLBValidBitsArray():
    return Array(Signal(TLB_NUM_WAYS, name="tlbvalid%d" % x) \
                for x in range(TLB_SET_SIZE))

def TLBTagEAArray():
    return Array(Signal(TLB_EA_TAG_BITS, name="tlbtagea%d" % x) \
                for x in range (TLB_NUM_WAYS))

def TLBTagsArray():
    return Array(Signal(TLB_TAG_WAY_BITS, name="tlbtags%d" % x) \
                for x in range (TLB_SET_SIZE))

def TLBPtesArray():
    return Array(Signal(TLB_PTE_WAY_BITS, name="tlbptes%d" % x) \
                for x in range(TLB_SET_SIZE))

def HitWaySet():
    return Array(Signal(WAY_BITS, name="hitway_%d" % x) \
                        for x in range(TLB_NUM_WAYS))

# Cache RAM interface
def CacheRamOut():
    return Array(Signal(WB_DATA_BITS, name="cache_out%d" % x) \
                 for x in range(NUM_WAYS))

# PLRU output interface
def PLRUOut():
    return Array(Signal(WAY_BITS, name="plru_out%d" % x) \
                for x in range(NUM_LINES))

# TLB PLRU output interface
def TLBPLRUOut():
    return Array(Signal(TLB_WAY_BITS, name="tlbplru_out%d" % x) \
                for x in range(TLB_SET_SIZE))

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
    return row[:ROW_BITS][:ROW_LINE_BITS]

# Returns whether this is the last row of a line
def is_last_row_addr(addr, last):
    return addr[ROW_OFF_BITS:LINE_OFF_BITS] == last

# Returns whether this is the last row of a line
def is_last_row(row, last):
    return get_row_of_line(row) == last

# Return the next row in the current cache line. We use a
# dedicated function in order to limit the size of the
# generated adder to be only the bits within a cache line
# (3 bits with default settings)
def next_row(row):
    row_v = row[0:ROW_LINE_BITS] + 1
    return Cat(row_v[:ROW_LINE_BITS], row[ROW_LINE_BITS:])

# Get the tag value from the address
def get_tag(addr):
    return addr[SET_SIZE_BITS:REAL_ADDR_BITS]

# Read a tag from a tag memory row
def read_tag(way, tagset):
    return tagset.word_select(way, TAG_WIDTH)[:TAG_BITS]

# Read a TLB tag from a TLB tag memory row
def read_tlb_tag(way, tags):
    return tags.word_select(way, TLB_EA_TAG_BITS)

# Write a TLB tag to a TLB tag memory row
def write_tlb_tag(way, tags, tag):
    return read_tlb_tag(way, tags).eq(tag)

# Read a PTE from a TLB PTE memory row
def read_tlb_pte(way, ptes):
    return ptes.word_select(way, TLB_PTE_BITS)

def write_tlb_pte(way, ptes, newpte):
    return read_tlb_pte(way, ptes).eq(newpte)


# Record for storing permission, attribute, etc. bits from a PTE
class PermAttr(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.reference = Signal()
        self.changed   = Signal()
        self.nocache   = Signal()
        self.priv      = Signal()
        self.rd_perm   = Signal()
        self.wr_perm   = Signal()


def extract_perm_attr(pte):
    pa = PermAttr()
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
    def __init__(self, name=None):
        super().__init__(name=name)
        self.req     = LoadStore1ToDCacheType(name="lsmem")
        self.tlbie   = Signal() # indicates a tlbie request (from MMU)
        self.doall   = Signal() # with tlbie, indicates flush whole TLB
        self.tlbld   = Signal() # indicates a TLB load request (from MMU)
        self.mmu_req = Signal() # indicates source of request
        self.d_valid = Signal() # indicates req.data is valid now


class MemAccessRequest(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.op        = Signal(Op)
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
    def __init__(self, name=None):
        super().__init__(name=name)
        # Info about the request
        self.full             = Signal() # have uncompleted request
        self.mmu_req          = Signal() # request is from MMU
        self.req              = MemAccessRequest(name="reqmem")

        # Cache hit state
        self.hit_way          = Signal(WAY_BITS)
        self.hit_load_valid   = Signal()
        self.hit_index        = Signal(INDEX_BITS)
        self.cache_hit        = Signal()

        # TLB hit state
        self.tlb_hit          = Signal()
        self.tlb_hit_way      = Signal(TLB_NUM_WAYS)
        self.tlb_hit_index    = Signal(TLB_WAY_BITS)

        # 2-stage data buffer for data forwarded from writes to reads
        self.forward_data1    = Signal(64)
        self.forward_data2    = Signal(64)
        self.forward_sel1     = Signal(8)
        self.forward_valid1   = Signal()
        self.forward_way1     = Signal(WAY_BITS)
        self.forward_row1     = Signal(ROW_BITS)
        self.use_forward1     = Signal()
        self.forward_sel      = Signal(8)

        # Cache miss state (reload state machine)
        self.state            = Signal(State)
        self.dcbz             = Signal()
        self.write_bram       = Signal()
        self.write_tag        = Signal()
        self.slow_valid       = Signal()
        self.wb               = WBMasterOut("wb")
        self.reload_tag       = Signal(TAG_BITS)
        self.store_way        = Signal(WAY_BITS)
        self.store_row        = Signal(ROW_BITS)
        self.store_index      = Signal(INDEX_BITS)
        self.end_row_ix       = Signal(ROW_LINE_BITS)
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
        self.valid = Signal()
        self.addr  = Signal(64-LINE_OFF_BITS)


class DTLBUpdate(Elaboratable):
    def __init__(self):
        self.tlbie    = Signal()
        self.tlbwe    = Signal()
        self.doall    = Signal()
        self.updated  = Signal()
        self.v_updated  = Signal()
        self.tlb_hit    = Signal()
        self.tlb_req_index = Signal(TLB_SET_BITS)

        self.tlb_hit_way     = Signal(TLB_WAY_BITS)
        self.tlb_tag_way     = Signal(TLB_TAG_WAY_BITS)
        self.tlb_pte_way     = Signal(TLB_PTE_WAY_BITS)
        self.repl_way        = Signal(TLB_WAY_BITS)
        self.eatag           = Signal(TLB_EA_TAG_BITS)
        self.pte_data        = Signal(TLB_PTE_BITS)

        self.dv = Signal(TLB_NUM_WAYS) # tlb_way_valids_t

        self.tb_out = Signal(TLB_TAG_WAY_BITS) # tlb_way_tags_t
        self.pb_out = Signal(TLB_NUM_WAYS)     # tlb_way_valids_t
        self.db_out = Signal(TLB_PTE_WAY_BITS) # tlb_way_ptes_t

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        tagset   = Signal(TLB_TAG_WAY_BITS)
        pteset   = Signal(TLB_PTE_WAY_BITS)

        tb_out, pb_out, db_out = self.tb_out, self.pb_out, self.db_out
        comb += db_out.eq(self.dv)

        with m.If(self.tlbie & self.doall):
            pass # clear all back in parent
        with m.Elif(self.tlbie):
            with m.If(self.tlb_hit):
                comb += db_out.bit_select(self.tlb_hit_way, 1).eq(1)
                comb += self.v_updated.eq(1)

        with m.Elif(self.tlbwe):

            comb += tagset.eq(self.tlb_tag_way)
            comb += write_tlb_tag(self.repl_way, tagset, self.eatag)
            comb += tb_out.eq(tagset)

            comb += pteset.eq(self.tlb_pte_way)
            comb += write_tlb_pte(self.repl_way, pteset, self.pte_data)
            comb += pb_out.eq(pteset)

            comb += db_out.bit_select(self.repl_way, 1).eq(1)

            comb += self.updated.eq(1)
            comb += self.v_updated.eq(1)

        return m


class DCachePendingHit(Elaboratable):

    def __init__(self, tlb_pte_way, tlb_valid_way, tlb_hit_way,
                      cache_valid_idx, cache_tag_set,
                    req_addr,
                    hit_set):

        self.go          = Signal()
        self.virt_mode   = Signal()
        self.is_hit      = Signal()
        self.tlb_hit     = Signal()
        self.hit_way     = Signal(WAY_BITS)
        self.rel_match   = Signal()
        self.req_index   = Signal(INDEX_BITS)
        self.reload_tag  = Signal(TAG_BITS)

        self.tlb_hit_way = tlb_hit_way
        self.tlb_pte_way = tlb_pte_way
        self.tlb_valid_way = tlb_valid_way
        self.cache_valid_idx = cache_valid_idx
        self.cache_tag_set = cache_tag_set
        self.req_addr = req_addr
        self.hit_set = hit_set

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        go = self.go
        virt_mode = self.virt_mode
        is_hit = self.is_hit
        tlb_pte_way = self.tlb_pte_way
        tlb_valid_way = self.tlb_valid_way
        cache_valid_idx = self.cache_valid_idx
        cache_tag_set = self.cache_tag_set
        req_addr = self.req_addr
        tlb_hit_way = self.tlb_hit_way
        tlb_hit = self.tlb_hit
        hit_set = self.hit_set
        hit_way = self.hit_way
        rel_match = self.rel_match
        req_index = self.req_index
        reload_tag = self.reload_tag

        rel_matches = Array(Signal(name="rel_matches_%d" % i) \
                                    for i in range(TLB_NUM_WAYS))
        hit_way_set = HitWaySet()

        # Test if pending request is a hit on any way
        # In order to make timing in virtual mode,
        # when we are using the TLB, we compare each
        # way with each of the real addresses from each way of
        # the TLB, and then decide later which match to use.

        with m.If(virt_mode):
            for j in range(TLB_NUM_WAYS): # tlb_num_way_t
                s_tag       = Signal(TAG_BITS, name="s_tag%d" % j)
                s_hit       = Signal()
                s_pte       = Signal(TLB_PTE_BITS)
                s_ra        = Signal(REAL_ADDR_BITS)
                comb += s_pte.eq(read_tlb_pte(j, tlb_pte_way))
                comb += s_ra.eq(Cat(req_addr[0:TLB_LG_PGSZ],
                                    s_pte[TLB_LG_PGSZ:REAL_ADDR_BITS]))
                comb += s_tag.eq(get_tag(s_ra))

                for i in range(NUM_WAYS): # way_t
                    is_tag_hit = Signal(name="is_tag_hit_%d_%d" % (j, i))
                    comb += is_tag_hit.eq(go & cache_valid_idx[i] &
                                  (read_tag(i, cache_tag_set) == s_tag)
                                  & tlb_valid_way[j])
                    with m.If(is_tag_hit):
                        comb += hit_way_set[j].eq(i)
                        comb += s_hit.eq(1)
                comb += hit_set[j].eq(s_hit)
                with m.If(s_tag == reload_tag):
                    comb += rel_matches[j].eq(1)
            with m.If(tlb_hit):
                comb += is_hit.eq(hit_set[tlb_hit_way])
                comb += hit_way.eq(hit_way_set[tlb_hit_way])
                comb += rel_match.eq(rel_matches[tlb_hit_way])
        with m.Else():
            s_tag       = Signal(TAG_BITS)
            comb += s_tag.eq(get_tag(req_addr))
            for i in range(NUM_WAYS): # way_t
                is_tag_hit = Signal(name="is_tag_hit_%d" % i)
                comb += is_tag_hit.eq(go & cache_valid_idx[i] &
                          (read_tag(i, cache_tag_set) == s_tag))
                with m.If(is_tag_hit):
                    comb += hit_way.eq(i)
                    comb += is_hit.eq(1)
            with m.If(s_tag == reload_tag):
                comb += rel_match.eq(1)

        return m


class DCache(Elaboratable):
    """Set associative dcache write-through
    TODO (in no specific order):
    * See list in icache.vhdl
    * Complete load misses on the cycle when WB data comes instead of
      at the end of line (this requires dealing with requests coming in
      while not idle...)
    """
    def __init__(self):
        self.d_in      = LoadStore1ToDCacheType("d_in")
        self.d_out     = DCacheToLoadStore1Type("d_out")

        self.m_in      = MMUToDCacheType("m_in")
        self.m_out     = DCacheToMMUType("m_out")

        self.stall_out = Signal()

        self.wb_out    = WBMasterOut("wb_out")
        self.wb_in     = WBSlaveOut("wb_in")

        self.log_out   = Signal(20)

    def stage_0(self, m, r0, r1, r0_full):
        """Latch the request in r0.req as long as we're not stalling
        """
        comb = m.d.comb
        sync = m.d.sync
        d_in, d_out, m_in = self.d_in, self.d_out, self.m_in

        r = RegStage0("stage0")

        # TODO, this goes in unit tests and formal proofs
        with m.If(d_in.valid & m_in.valid):
            sync += Display("request collision loadstore vs MMU")

        with m.If(m_in.valid):
            comb += r.req.valid.eq(1)
            comb += r.req.load.eq(~(m_in.tlbie | m_in.tlbld))
            comb += r.req.dcbz.eq(0)
            comb += r.req.nc.eq(0)
            comb += r.req.reserve.eq(0)
            comb += r.req.virt_mode.eq(0)
            comb += r.req.priv_mode.eq(1)
            comb += r.req.addr.eq(m_in.addr)
            comb += r.req.data.eq(m_in.pte)
            comb += r.req.byte_sel.eq(~0) # Const -1 sets all to 0b111....
            comb += r.tlbie.eq(m_in.tlbie)
            comb += r.doall.eq(m_in.doall)
            comb += r.tlbld.eq(m_in.tlbld)
            comb += r.mmu_req.eq(1)
        with m.Else():
            comb += r.req.eq(d_in)
            comb += r.req.data.eq(0)
            comb += r.tlbie.eq(0)
            comb += r.doall.eq(0)
            comb += r.tlbld.eq(0)
            comb += r.mmu_req.eq(0)
        with m.If((~r1.full & ~d_in.hold) | ~r0_full):
            sync += r0.eq(r)
            sync += r0_full.eq(r.req.valid)
            # Sample data the cycle after a request comes in from loadstore1.
            # If another request has come in already then the data will get
            # put directly into req.data below.
            with m.If(r0.req.valid & ~r.req.valid & ~r0.d_valid &
                     ~r0.mmu_req):
                sync += r0.req.data.eq(d_in.data)
                sync += r0.d_valid.eq(1)

    def tlb_read(self, m, r0_stall, tlb_valid_way,
                 tlb_tag_way, tlb_pte_way, dtlb_valid_bits,
                 dtlb_tags, dtlb_ptes):
        """TLB
        Operates in the second cycle on the request latched in r0.req.
        TLB updates write the entry at the end of the second cycle.
        """
        comb = m.d.comb
        sync = m.d.sync
        m_in, d_in = self.m_in, self.d_in

        index    = Signal(TLB_SET_BITS)
        addrbits = Signal(TLB_SET_BITS)

        amin = TLB_LG_PGSZ
        amax = TLB_LG_PGSZ + TLB_SET_BITS

        with m.If(m_in.valid):
            comb += addrbits.eq(m_in.addr[amin : amax])
        with m.Else():
            comb += addrbits.eq(d_in.addr[amin : amax])
        comb += index.eq(addrbits)

        # If we have any op and the previous op isn't finished,
        # then keep the same output for next cycle.
        with m.If(~r0_stall):
            sync += tlb_valid_way.eq(dtlb_valid_bits[index])
            sync += tlb_tag_way.eq(dtlb_tags[index])
            sync += tlb_pte_way.eq(dtlb_ptes[index])

    def maybe_tlb_plrus(self, m, r1, tlb_plru_victim):
        """Generate TLB PLRUs
        """
        comb = m.d.comb
        sync = m.d.sync

        if TLB_NUM_WAYS == 0:
            return
        for i in range(TLB_SET_SIZE):
            # TLB PLRU interface
            tlb_plru        = PLRU(TLB_WAY_BITS)
            setattr(m.submodules, "maybe_plru_%d" % i, tlb_plru)
            tlb_plru_acc_en = Signal()

            comb += tlb_plru_acc_en.eq(r1.tlb_hit & (r1.tlb_hit_index == i))
            comb += tlb_plru.acc_en.eq(tlb_plru_acc_en)
            comb += tlb_plru.acc_i.eq(r1.tlb_hit_way)
            comb += tlb_plru_victim[i].eq(tlb_plru.lru_o)

    def tlb_search(self, m, tlb_req_index, r0, r0_valid,
                   tlb_valid_way, tlb_tag_way, tlb_hit_way,
                   tlb_pte_way, pte, tlb_hit, valid_ra, perm_attr, ra):

        comb = m.d.comb

        hitway = Signal(TLB_WAY_BITS)
        hit    = Signal()
        eatag  = Signal(TLB_EA_TAG_BITS)

        TLB_LG_END = TLB_LG_PGSZ + TLB_SET_BITS
        comb += tlb_req_index.eq(r0.req.addr[TLB_LG_PGSZ : TLB_LG_END])
        comb += eatag.eq(r0.req.addr[TLB_LG_END : 64 ])

        for i in range(TLB_NUM_WAYS):
            is_tag_hit = Signal()
            comb += is_tag_hit.eq(tlb_valid_way[i]
                                  & (read_tlb_tag(i, tlb_tag_way) == eatag))
            with m.If(is_tag_hit):
                comb += hitway.eq(i)
                comb += hit.eq(1)

        comb += tlb_hit.eq(hit & r0_valid)
        comb += tlb_hit_way.eq(hitway)

        with m.If(tlb_hit):
            comb += pte.eq(read_tlb_pte(hitway, tlb_pte_way))
        comb += valid_ra.eq(tlb_hit | ~r0.req.virt_mode)

        with m.If(r0.req.virt_mode):
            comb += ra.eq(Cat(Const(0, ROW_OFF_BITS),
                              r0.req.addr[ROW_OFF_BITS:TLB_LG_PGSZ],
                              pte[TLB_LG_PGSZ:REAL_ADDR_BITS]))
            comb += perm_attr.reference.eq(pte[8])
            comb += perm_attr.changed.eq(pte[7])
            comb += perm_attr.nocache.eq(pte[5])
            comb += perm_attr.priv.eq(pte[3])
            comb += perm_attr.rd_perm.eq(pte[2])
            comb += perm_attr.wr_perm.eq(pte[1])
        with m.Else():
            comb += ra.eq(Cat(Const(0, ROW_OFF_BITS),
                              r0.req.addr[ROW_OFF_BITS:REAL_ADDR_BITS]))
            comb += perm_attr.reference.eq(1)
            comb += perm_attr.changed.eq(1)
            comb += perm_attr.nocache.eq(0)
            comb += perm_attr.priv.eq(1)
            comb += perm_attr.rd_perm.eq(1)
            comb += perm_attr.wr_perm.eq(1)

    def tlb_update(self, m, r0_valid, r0, dtlb_valid_bits, tlb_req_index,
                    tlb_hit_way, tlb_hit, tlb_plru_victim, tlb_tag_way,
                    dtlb_tags, tlb_pte_way, dtlb_ptes):

        dtlb_valids = TLBValidBitsArray()

        comb = m.d.comb
        sync = m.d.sync

        tlbie    = Signal()
        tlbwe    = Signal()

        comb += tlbie.eq(r0_valid & r0.tlbie)
        comb += tlbwe.eq(r0_valid & r0.tlbld)

        m.submodules.tlb_update = d = DTLBUpdate()
        with m.If(tlbie & r0.doall):
            # clear all valid bits at once
            for i in range(TLB_SET_SIZE):
                sync += dtlb_valid_bits[i].eq(0)
        with m.If(d.updated):
            sync += dtlb_tags[tlb_req_index].eq(d.tb_out)
            sync += dtlb_ptes[tlb_req_index].eq(d.pb_out)
        with m.If(d.v_updated):
            sync += dtlb_valid_bits[tlb_req_index].eq(d.db_out)

        comb += d.dv.eq(dtlb_valid_bits[tlb_req_index])

        comb += d.tlbie.eq(tlbie)
        comb += d.tlbwe.eq(tlbwe)
        comb += d.doall.eq(r0.doall)
        comb += d.tlb_hit.eq(tlb_hit)
        comb += d.tlb_hit_way.eq(tlb_hit_way)
        comb += d.tlb_tag_way.eq(tlb_tag_way)
        comb += d.tlb_pte_way.eq(tlb_pte_way)
        comb += d.tlb_req_index.eq(tlb_req_index)

        with m.If(tlb_hit):
            comb += d.repl_way.eq(tlb_hit_way)
        with m.Else():
            comb += d.repl_way.eq(tlb_plru_victim[tlb_req_index])
        comb += d.eatag.eq(r0.req.addr[TLB_LG_PGSZ + TLB_SET_BITS:64])
        comb += d.pte_data.eq(r0.req.data)

    def maybe_plrus(self, m, r1, plru_victim):
        """Generate PLRUs
        """
        comb = m.d.comb
        sync = m.d.sync

        if TLB_NUM_WAYS == 0:
            return

        for i in range(NUM_LINES):
            # PLRU interface
            plru        = PLRU(WAY_BITS)
            setattr(m.submodules, "plru%d" % i, plru)
            plru_acc_en = Signal()

            comb += plru_acc_en.eq(r1.cache_hit & (r1.hit_index == i))
            comb += plru.acc_en.eq(plru_acc_en)
            comb += plru.acc_i.eq(r1.hit_way)
            comb += plru_victim[i].eq(plru.lru_o)

    def cache_tag_read(self, m, r0_stall, req_index, cache_tag_set, cache_tags):
        """Cache tag RAM read port
        """
        comb = m.d.comb
        sync = m.d.sync
        m_in, d_in = self.m_in, self.d_in

        index = Signal(INDEX_BITS)

        with m.If(r0_stall):
            comb += index.eq(req_index)
        with m.Elif(m_in.valid):
            comb += index.eq(get_index(m_in.addr))
        with m.Else():
            comb += index.eq(get_index(d_in.addr))
        sync += cache_tag_set.eq(cache_tags[index])

    def dcache_request(self, m, r0, ra, req_index, req_row, req_tag,
                       r0_valid, r1, cache_valids, replace_way,
                       use_forward1_next, use_forward2_next,
                       req_hit_way, plru_victim, rc_ok, perm_attr,
                       valid_ra, perm_ok, access_ok, req_op, req_go,
                       tlb_pte_way,
                       tlb_hit, tlb_hit_way, tlb_valid_way, cache_tag_set,
                       cancel_store, req_same_tag, r0_stall, early_req_row):
        """Cache request parsing and hit detection
        """

        comb = m.d.comb
        m_in, d_in = self.m_in, self.d_in

        is_hit      = Signal()
        hit_way     = Signal(WAY_BITS)
        op          = Signal(Op)
        opsel       = Signal(3)
        go          = Signal()
        nc          = Signal()
        hit_set     = Array(Signal(name="hit_set_%d" % i) \
                                  for i in range(TLB_NUM_WAYS))
        cache_valid_idx = Signal(NUM_WAYS)

        # Extract line, row and tag from request
        comb += req_index.eq(get_index(r0.req.addr))
        comb += req_row.eq(get_row(r0.req.addr))
        comb += req_tag.eq(get_tag(ra))

        if False: # display on comb is a bit... busy.
            comb += Display("dcache_req addr:%x ra: %x idx: %x tag: %x row: %x",
                    r0.req.addr, ra, req_index, req_tag, req_row)

        comb += go.eq(r0_valid & ~(r0.tlbie | r0.tlbld) & ~r1.ls_error)
        comb += cache_valid_idx.eq(cache_valids[req_index])

        m.submodules.dcache_pend = dc = DCachePendingHit(tlb_pte_way,
                                tlb_valid_way, tlb_hit_way,
                                cache_valid_idx, cache_tag_set,
                                r0.req.addr,
                                hit_set)

        comb += dc.tlb_hit.eq(tlb_hit)
        comb += dc.reload_tag.eq(r1.reload_tag)
        comb += dc.virt_mode.eq(r0.req.virt_mode)
        comb += dc.go.eq(go)
        comb += dc.req_index.eq(req_index)
        comb += is_hit.eq(dc.is_hit)
        comb += hit_way.eq(dc.hit_way)
        comb += req_same_tag.eq(dc.rel_match)

        # See if the request matches the line currently being reloaded
        with m.If((r1.state == State.RELOAD_WAIT_ACK) &
                  (req_index == r1.store_index) & req_same_tag):
            # For a store, consider this a hit even if the row isn't
            # valid since it will be by the time we perform the store.
            # For a load, check the appropriate row valid bit.
            rrow = Signal(ROW_LINE_BITS)
            comb += rrow.eq(req_row)
            valid = r1.rows_valid[rrow]
            comb += is_hit.eq((~r0.req.load) | valid)
            comb += hit_way.eq(replace_way)

        # Whether to use forwarded data for a load or not
        with m.If((get_row(r1.req.real_addr) == req_row) &
                  (r1.req.hit_way == hit_way)):
            # Only need to consider r1.write_bram here, since if we
            # are writing refill data here, then we don't have a
            # cache hit this cycle on the line being refilled.
            # (There is the possibility that the load following the
            # load miss that started the refill could be to the old
            # contents of the victim line, since it is a couple of
            # cycles after the refill starts before we see the updated
            # cache tag. In that case we don't use the bypass.)
            comb += use_forward1_next.eq(r1.write_bram)
        with m.If((r1.forward_row1 == req_row) & (r1.forward_way1 == hit_way)):
            comb += use_forward2_next.eq(r1.forward_valid1)

        # The way that matched on a hit
        comb += req_hit_way.eq(hit_way)

        # The way to replace on a miss
        with m.If(r1.write_tag):
            comb += replace_way.eq(plru_victim[r1.store_index])
        with m.Else():
            comb += replace_way.eq(r1.store_way)

        # work out whether we have permission for this access
        # NB we don't yet implement AMR, thus no KUAP
        comb += rc_ok.eq(perm_attr.reference
                         & (r0.req.load | perm_attr.changed))
        comb += perm_ok.eq((r0.req.priv_mode | (~perm_attr.priv)) &
                           (perm_attr.wr_perm |
                              (r0.req.load & perm_attr.rd_perm)))
        comb += access_ok.eq(valid_ra & perm_ok & rc_ok)
        # Combine the request and cache hit status to decide what
        # operation needs to be done
        comb += nc.eq(r0.req.nc | perm_attr.nocache)
        comb += op.eq(Op.OP_NONE)
        with m.If(go):
            with m.If(~access_ok):
                comb += op.eq(Op.OP_BAD)
            with m.Elif(cancel_store):
                comb += op.eq(Op.OP_STCX_FAIL)
            with m.Else():
                comb += opsel.eq(Cat(is_hit, nc, r0.req.load))
                with m.Switch(opsel):
                    with m.Case(0b101): comb += op.eq(Op.OP_LOAD_HIT)
                    with m.Case(0b100): comb += op.eq(Op.OP_LOAD_MISS)
                    with m.Case(0b110): comb += op.eq(Op.OP_LOAD_NC)
                    with m.Case(0b001): comb += op.eq(Op.OP_STORE_HIT)
                    with m.Case(0b000): comb += op.eq(Op.OP_STORE_MISS)
                    with m.Case(0b010): comb += op.eq(Op.OP_STORE_MISS)
                    with m.Case(0b011): comb += op.eq(Op.OP_BAD)
                    with m.Case(0b111): comb += op.eq(Op.OP_BAD)
        comb += req_op.eq(op)
        comb += req_go.eq(go)

        # Version of the row number that is valid one cycle earlier
        # in the cases where we need to read the cache data BRAM.
        # If we're stalling then we need to keep reading the last
        # row requested.
        with m.If(~r0_stall):
            with m.If(m_in.valid):
                comb += early_req_row.eq(get_row(m_in.addr))
            with m.Else():
                comb += early_req_row.eq(get_row(d_in.addr))
        with m.Else():
            comb += early_req_row.eq(req_row)

    def reservation_comb(self, m, cancel_store, set_rsrv, clear_rsrv,
                         r0_valid, r0, reservation):
        """Handle load-with-reservation and store-conditional instructions
        """
        comb = m.d.comb

        with m.If(r0_valid & r0.req.reserve):
            # XXX generate alignment interrupt if address
            # is not aligned XXX or if r0.req.nc = '1'
            with m.If(r0.req.load):
                comb += set_rsrv.eq(r0.req.atomic_last) # load with reservation
            with m.Else():
                comb += clear_rsrv.eq(r0.req.atomic_last) # store conditional
                with m.If((~reservation.valid) |
                         (r0.req.addr[LINE_OFF_BITS:64] != reservation.addr)):
                    comb += cancel_store.eq(1)

    def reservation_reg(self, m, r0_valid, access_ok, set_rsrv, clear_rsrv,
                        reservation, r0):

        comb = m.d.comb
        sync = m.d.sync

        with m.If(r0_valid & access_ok):
            with m.If(clear_rsrv):
                sync += reservation.valid.eq(0)
            with m.Elif(set_rsrv):
                sync += reservation.valid.eq(1)
                sync += reservation.addr.eq(r0.req.addr[LINE_OFF_BITS:64])

    def writeback_control(self, m, r1, cache_out_row):
        """Return data for loads & completion control logic
        """
        comb = m.d.comb
        sync = m.d.sync
        d_out, m_out = self.d_out, self.m_out

        data_out = Signal(64)
        data_fwd = Signal(64)

        # Use the bypass if are reading the row that was
        # written 1 or 2 cycles ago, including for the
        # slow_valid = 1 case (i.e. completing a load
        # miss or a non-cacheable load).
        with m.If(r1.use_forward1):
            comb += data_fwd.eq(r1.forward_data1)
        with m.Else():
            comb += data_fwd.eq(r1.forward_data2)

        comb += data_out.eq(cache_out_row)

        for i in range(8):
            with m.If(r1.forward_sel[i]):
                dsel = data_fwd.word_select(i, 8)
                comb += data_out.word_select(i, 8).eq(dsel)

        comb += d_out.valid.eq(r1.ls_valid)
        comb += d_out.data.eq(data_out)
        comb += d_out.store_done.eq(~r1.stcx_fail)
        comb += d_out.error.eq(r1.ls_error)
        comb += d_out.cache_paradox.eq(r1.cache_paradox)

        # Outputs to MMU
        comb += m_out.done.eq(r1.mmu_done)
        comb += m_out.err.eq(r1.mmu_error)
        comb += m_out.data.eq(data_out)

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

        if False: # TODO: need Display to get this to work
            assert (r1.slow_valid & r1.stcx_fail) != 1, \
            "unexpected slow_valid collision with stcx_fail"

            assert ((r1.slow_valid | r1.stcx_fail) | r1.hit_load_valid) != 1, \
             "unexpected hit_load_delayed collision with slow_valid"

        with m.If(~r1.mmu_req):
            # Request came from loadstore1...
            # Load hit case is the standard path
            with m.If(r1.hit_load_valid):
                sync += Display("completing load hit data=%x", data_out)

            # error cases complete without stalling
            with m.If(r1.ls_error):
                sync += Display("completing ld/st with error")

            # Slow ops (load miss, NC, stores)
            with m.If(r1.slow_valid):
                sync += Display("completing store or load miss adr=%x data=%x",
                                r1.req.real_addr, data_out)

        with m.Else():
            # Request came from MMU
            with m.If(r1.hit_load_valid):
                sync += Display("completing load hit to MMU, data=%x",
                                m_out.data)
            # error cases complete without stalling
            with m.If(r1.mmu_error):
                sync += Display("combpleting MMU ld with error")

            # Slow ops (i.e. load miss)
            with m.If(r1.slow_valid):
                sync += Display("completing MMU load miss, data=%x",
                                m_out.data)

    def rams(self, m, r1, early_req_row, cache_out_row, replace_way):
        """rams
        Generate a cache RAM for each way. This handles the normal
        reads, writes from reloads and the special store-hit update
        path as well.

        Note: the BRAMs have an extra read buffer, meaning the output
        is pipelined an extra cycle. This differs from the
        icache. The writeback logic needs to take that into
        account by using 1-cycle delayed signals for load hits.
        """
        comb = m.d.comb
        wb_in = self.wb_in

        for i in range(NUM_WAYS):
            do_read  = Signal(name="do_rd%d" % i)
            rd_addr  = Signal(ROW_BITS, name="rd_addr_%d" % i)
            do_write = Signal(name="do_wr%d" % i)
            wr_addr  = Signal(ROW_BITS, name="wr_addr_%d" % i)
            wr_data  = Signal(WB_DATA_BITS, name="din_%d" % i)
            wr_sel   = Signal(ROW_SIZE)
            wr_sel_m = Signal(ROW_SIZE)
            _d_out   = Signal(WB_DATA_BITS, name="dout_%d" % i) # cache_row_t

            way = CacheRam(ROW_BITS, WB_DATA_BITS, ADD_BUF=True)
            setattr(m.submodules, "cacheram_%d" % i, way)

            comb += way.rd_en.eq(do_read)
            comb += way.rd_addr.eq(rd_addr)
            comb += _d_out.eq(way.rd_data_o)
            comb += way.wr_sel.eq(wr_sel_m)
            comb += way.wr_addr.eq(wr_addr)
            comb += way.wr_data.eq(wr_data)

            # Cache hit reads
            comb += do_read.eq(1)
            comb += rd_addr.eq(early_req_row)
            with m.If(r1.hit_way == i):
                comb += cache_out_row.eq(_d_out)

            # Write mux:
            #
            # Defaults to wishbone read responses (cache refill)
            #
            # For timing, the mux on wr_data/sel/addr is not
            # dependent on anything other than the current state.

            with m.If(r1.write_bram):
                # Write store data to BRAM.  This happens one
                # cycle after the store is in r0.
                comb += wr_data.eq(r1.req.data)
                comb += wr_sel.eq(r1.req.byte_sel)
                comb += wr_addr.eq(get_row(r1.req.real_addr))

                with m.If(i == r1.req.hit_way):
                    comb += do_write.eq(1)
            with m.Else():
                # Otherwise, we might be doing a reload or a DCBZ
                with m.If(r1.dcbz):
                    comb += wr_data.eq(0)
                with m.Else():
                    comb += wr_data.eq(wb_in.dat)
                comb += wr_addr.eq(r1.store_row)
                comb += wr_sel.eq(~0) # all 1s

                with m.If((r1.state == State.RELOAD_WAIT_ACK)
                          & wb_in.ack & (replace_way == i)):
                    comb += do_write.eq(1)

            # Mask write selects with do_write since BRAM
            # doesn't have a global write-enable
            with m.If(do_write):
                comb += wr_sel_m.eq(wr_sel)

    # Cache hit synchronous machine for the easy case.
    # This handles load hits.
    # It also handles error cases (TLB miss, cache paradox)
    def dcache_fast_hit(self, m, req_op, r0_valid, r0, r1,
                        req_hit_way, req_index, req_tag, access_ok,
                        tlb_hit, tlb_hit_way, tlb_req_index):

        comb = m.d.comb
        sync = m.d.sync

        with m.If(req_op != Op.OP_NONE):
            sync += Display("op:%d addr:%x nc: %d idx: %x tag: %x way: %x",
                    req_op, r0.req.addr, r0.req.nc,
                    req_index, req_tag, req_hit_way)

        with m.If(r0_valid):
            sync += r1.mmu_req.eq(r0.mmu_req)

        # Fast path for load/store hits.
        # Set signals for the writeback controls.
        sync += r1.hit_way.eq(req_hit_way)
        sync += r1.hit_index.eq(req_index)

        with m.If(req_op == Op.OP_LOAD_HIT):
            sync += r1.hit_load_valid.eq(1)
        with m.Else():
            sync += r1.hit_load_valid.eq(0)

        with m.If((req_op == Op.OP_LOAD_HIT) | (req_op == Op.OP_STORE_HIT)):
            sync += r1.cache_hit.eq(1)
        with m.Else():
            sync += r1.cache_hit.eq(0)

        with m.If(req_op == Op.OP_BAD):
            # Display(f"Signalling ld/st error valid_ra={valid_ra}"
            #      f"rc_ok={rc_ok} perm_ok={perm_ok}"
            sync += r1.ls_error.eq(~r0.mmu_req)
            sync += r1.mmu_error.eq(r0.mmu_req)
            sync += r1.cache_paradox.eq(access_ok)

            with m.Else():
                sync += r1.ls_error.eq(0)
                sync += r1.mmu_error.eq(0)
                sync += r1.cache_paradox.eq(0)

        with m.If(req_op == Op.OP_STCX_FAIL):
            sync += r1.stcx_fail.eq(1)
        with m.Else():
            sync += r1.stcx_fail.eq(0)

        # Record TLB hit information for updating TLB PLRU
        sync += r1.tlb_hit.eq(tlb_hit)
        sync += r1.tlb_hit_way.eq(tlb_hit_way)
        sync += r1.tlb_hit_index.eq(tlb_req_index)

    # Memory accesses are handled by this state machine:
    #
    #   * Cache load miss/reload (in conjunction with "rams")
    #   * Load hits for non-cachable forms
    #   * Stores (the collision case is handled in "rams")
    #
    # All wishbone requests generation is done here.
    # This machine operates at stage 1.
    def dcache_slow(self, m, r1, use_forward1_next, use_forward2_next,
                    cache_valids, r0, replace_way,
                    req_hit_way, req_same_tag,
                    r0_valid, req_op, cache_tags, req_go, ra):

        comb = m.d.comb
        sync = m.d.sync
        wb_in = self.wb_in
        d_in = self.d_in

        req         = MemAccessRequest("mreq_ds")

        req_row = Signal(ROW_BITS)
        req_idx = Signal(INDEX_BITS)
        req_tag = Signal(TAG_BITS)
        comb += req_idx.eq(get_index(req.real_addr))
        comb += req_row.eq(get_row(req.real_addr))
        comb += req_tag.eq(get_tag(req.real_addr))

        sync += r1.use_forward1.eq(use_forward1_next)
        sync += r1.forward_sel.eq(0)

        with m.If(use_forward1_next):
            sync += r1.forward_sel.eq(r1.req.byte_sel)
        with m.Elif(use_forward2_next):
            sync += r1.forward_sel.eq(r1.forward_sel1)

        sync += r1.forward_data2.eq(r1.forward_data1)
        with m.If(r1.write_bram):
            sync += r1.forward_data1.eq(r1.req.data)
            sync += r1.forward_sel1.eq(r1.req.byte_sel)
            sync += r1.forward_way1.eq(r1.req.hit_way)
            sync += r1.forward_row1.eq(get_row(r1.req.real_addr))
            sync += r1.forward_valid1.eq(1)
        with m.Else():
            with m.If(r1.dcbz):
                sync += r1.forward_data1.eq(0)
            with m.Else():
                sync += r1.forward_data1.eq(wb_in.dat)
            sync += r1.forward_sel1.eq(~0) # all 1s
            sync += r1.forward_way1.eq(replace_way)
            sync += r1.forward_row1.eq(r1.store_row)
            sync += r1.forward_valid1.eq(0)

        # One cycle pulses reset
        sync += r1.slow_valid.eq(0)
        sync += r1.write_bram.eq(0)
        sync += r1.inc_acks.eq(0)
        sync += r1.dec_acks.eq(0)

        sync += r1.ls_valid.eq(0)
        # complete tlbies and TLB loads in the third cycle
        sync += r1.mmu_done.eq(r0_valid & (r0.tlbie | r0.tlbld))

        with m.If((req_op == Op.OP_LOAD_HIT) | (req_op == Op.OP_STCX_FAIL)):
            with m.If(~r0.mmu_req):
                sync += r1.ls_valid.eq(1)
            with m.Else():
                sync += r1.mmu_done.eq(1)

        with m.If(r1.write_tag):
            # Store new tag in selected way
            for i in range(NUM_WAYS):
                with m.If(i == replace_way):
                    ct = Signal(TAG_RAM_WIDTH)
                    comb += ct.eq(cache_tags[r1.store_index])
                    """
TODO: check this
cache_tags(r1.store_index)((i + 1) * TAG_WIDTH - 1 downto i * TAG_WIDTH) <=
                    (TAG_WIDTH - 1 downto TAG_BITS => '0') & r1.reload_tag;
                    """
                    comb += ct.word_select(i, TAG_WIDTH).eq(r1.reload_tag)
                    sync += cache_tags[r1.store_index].eq(ct)
            sync += r1.store_way.eq(replace_way)
            sync += r1.write_tag.eq(0)

        # Take request from r1.req if there is one there,
        # else from req_op, ra, etc.
        with m.If(r1.full):
            comb += req.eq(r1.req)
        with m.Else():
            comb += req.op.eq(req_op)
            comb += req.valid.eq(req_go)
            comb += req.mmu_req.eq(r0.mmu_req)
            comb += req.dcbz.eq(r0.req.dcbz)
            comb += req.real_addr.eq(ra)

            with m.If(r0.req.dcbz):
                # force data to 0 for dcbz
                comb += req.data.eq(0)
            with m.Elif(r0.d_valid):
                comb += req.data.eq(r0.req.data)
            with m.Else():
                comb += req.data.eq(d_in.data)

            # Select all bytes for dcbz
            # and for cacheable loads
            with m.If(r0.req.dcbz | (r0.req.load & ~r0.req.nc)):
                comb += req.byte_sel.eq(~0) # all 1s
            with m.Else():
                comb += req.byte_sel.eq(r0.req.byte_sel)
            comb += req.hit_way.eq(req_hit_way)
            comb += req.same_tag.eq(req_same_tag)

            # Store the incoming request from r0,
            # if it is a slow request
            # Note that r1.full = 1 implies req_op = OP_NONE
            with m.If((req_op == Op.OP_LOAD_MISS)
                      | (req_op == Op.OP_LOAD_NC)
                      | (req_op == Op.OP_STORE_MISS)
                      | (req_op == Op.OP_STORE_HIT)):
                sync += r1.req.eq(req)
                sync += r1.full.eq(1)

        # Main state machine
        with m.Switch(r1.state):

            with m.Case(State.IDLE):
                sync += r1.wb.adr.eq(req.real_addr[ROW_LINE_BITS:])
                sync += r1.wb.sel.eq(req.byte_sel)
                sync += r1.wb.dat.eq(req.data)
                sync += r1.dcbz.eq(req.dcbz)

                # Keep track of our index and way
                # for subsequent stores.
                sync += r1.store_index.eq(req_idx)
                sync += r1.store_row.eq(req_row)
                sync += r1.end_row_ix.eq(get_row_of_line(req_row)-1)
                sync += r1.reload_tag.eq(req_tag)
                sync += r1.req.same_tag.eq(1)

                with m.If(req.op == Op.OP_STORE_HIT):
                    sync += r1.store_way.eq(req.hit_way)

                # Reset per-row valid bits,
                # ready for handling OP_LOAD_MISS
                for i in range(ROW_PER_LINE):
                    sync += r1.rows_valid[i].eq(0)

                with m.If(req_op != Op.OP_NONE):
                    sync += Display("cache op %d", req.op)

                with m.Switch(req.op):
                    with m.Case(Op.OP_LOAD_HIT):
                        # stay in IDLE state
                        pass

                    with m.Case(Op.OP_LOAD_MISS):
                        sync += Display("cache miss real addr: %x " \
                                "idx: %x tag: %x",
                                req.real_addr, req_row, req_tag)

                        # Start the wishbone cycle
                        sync += r1.wb.we.eq(0)
                        sync += r1.wb.cyc.eq(1)
                        sync += r1.wb.stb.eq(1)

                        # Track that we had one request sent
                        sync += r1.state.eq(State.RELOAD_WAIT_ACK)
                        sync += r1.write_tag.eq(1)

                    with m.Case(Op.OP_LOAD_NC):
                        sync += r1.wb.cyc.eq(1)
                        sync += r1.wb.stb.eq(1)
                        sync += r1.wb.we.eq(0)
                        sync += r1.state.eq(State.NC_LOAD_WAIT_ACK)

                    with m.Case(Op.OP_STORE_HIT, Op.OP_STORE_MISS):
                        with m.If(~req.dcbz):
                            sync += r1.state.eq(State.STORE_WAIT_ACK)
                            sync += r1.acks_pending.eq(1)
                            sync += r1.full.eq(0)
                            sync += r1.slow_valid.eq(1)

                            with m.If(~req.mmu_req):
                                sync += r1.ls_valid.eq(1)
                            with m.Else():
                                sync += r1.mmu_done.eq(1)

                            with m.If(req.op == Op.OP_STORE_HIT):
                                sync += r1.write_bram.eq(1)
                        with m.Else():
                            # dcbz is handled much like a load miss except
                            # that we are writing to memory instead of reading
                            sync += r1.state.eq(State.RELOAD_WAIT_ACK)

                            with m.If(req.op == Op.OP_STORE_MISS):
                                sync += r1.write_tag.eq(1)

                        sync += r1.wb.we.eq(1)
                        sync += r1.wb.cyc.eq(1)
                        sync += r1.wb.stb.eq(1)

                    # OP_NONE and OP_BAD do nothing
                    # OP_BAD & OP_STCX_FAIL were
                    # handled above already
                    with m.Case(Op.OP_NONE):
                        pass
                    with m.Case(Op.OP_BAD):
                        pass
                    with m.Case(Op.OP_STCX_FAIL):
                        pass

            with m.Case(State.RELOAD_WAIT_ACK):
                ld_stbs_done = Signal()
                # Requests are all sent if stb is 0
                comb += ld_stbs_done.eq(~r1.wb.stb)

                # If we are still sending requests, was one accepted?
                with m.If((~wb_in.stall) & r1.wb.stb):
                    # That was the last word?  We are done sending.
                    # Clear stb and set ld_stbs_done so we can handle an
                    # eventual last ack on the same cycle.
                    # sigh - reconstruct wb adr with 3 extra 0s at front
                    wb_adr = Cat(Const(0, ROW_OFF_BITS), r1.wb.adr)
                    with m.If(is_last_row_addr(wb_adr, r1.end_row_ix)):
                        sync += r1.wb.stb.eq(0)
                        comb += ld_stbs_done.eq(1)

                    # Calculate the next row address in the current cache line
                    row = Signal(LINE_OFF_BITS-ROW_OFF_BITS)
                    comb += row.eq(r1.wb.adr)
                    sync += r1.wb.adr[:LINE_OFF_BITS-ROW_OFF_BITS].eq(row+1)

                # Incoming acks processing
                sync += r1.forward_valid1.eq(wb_in.ack)
                with m.If(wb_in.ack):
                    srow = Signal(ROW_LINE_BITS)
                    comb += srow.eq(r1.store_row)
                    sync += r1.rows_valid[srow].eq(1)

                    # If this is the data we were looking for,
                    # we can complete the request next cycle.
                    # Compare the whole address in case the
                    # request in r1.req is not the one that
                    # started this refill.
                    with m.If(req.valid & r1.req.same_tag &
                              ((r1.dcbz & r1.req.dcbz) |
                               (~r1.dcbz & (r1.req.op == Op.OP_LOAD_MISS))) &
                                (r1.store_row == get_row(req.real_addr))):
                        sync += r1.full.eq(0)
                        sync += r1.slow_valid.eq(1)
                        with m.If(~r1.mmu_req):
                            sync += r1.ls_valid.eq(1)
                        with m.Else():
                            sync += r1.mmu_done.eq(1)
                        sync += r1.forward_sel.eq(~0) # all 1s
                        sync += r1.use_forward1.eq(1)

                    # Check for completion
                    with m.If(ld_stbs_done & is_last_row(r1.store_row,
                                                      r1.end_row_ix)):
                        # Complete wishbone cycle
                        sync += r1.wb.cyc.eq(0)

                        # Cache line is now valid
                        cv = Signal(INDEX_BITS)
                        comb += cv.eq(cache_valids[r1.store_index])
                        comb += cv.bit_select(r1.store_way, 1).eq(1)
                        sync += cache_valids[r1.store_index].eq(cv)

                        sync += r1.state.eq(State.IDLE)

                    # Increment store row counter
                    sync += r1.store_row.eq(next_row(r1.store_row))

            with m.Case(State.STORE_WAIT_ACK):
                st_stbs_done = Signal()
                acks        = Signal(3)
                adjust_acks = Signal(3)

                comb += st_stbs_done.eq(~r1.wb.stb)
                comb += acks.eq(r1.acks_pending)

                with m.If(r1.inc_acks != r1.dec_acks):
                    with m.If(r1.inc_acks):
                        comb += adjust_acks.eq(acks + 1)
                    with m.Else():
                        comb += adjust_acks.eq(acks - 1)
                with m.Else():
                    comb += adjust_acks.eq(acks)

                sync += r1.acks_pending.eq(adjust_acks)

                # Clear stb when slave accepted request
                with m.If(~wb_in.stall):
                    # See if there is another store waiting
                    # to be done which is in the same real page.
                    with m.If(req.valid):
                        _ra = req.real_addr[ROW_LINE_BITS:SET_SIZE_BITS]
                        sync += r1.wb.adr[0:SET_SIZE_BITS].eq(_ra)
                        sync += r1.wb.dat.eq(req.data)
                        sync += r1.wb.sel.eq(req.byte_sel)

                    with m.If((adjust_acks < 7) & req.same_tag &
                                ((req.op == Op.OP_STORE_MISS)
                                 | (req.op == Op.OP_STORE_HIT))):
                        sync += r1.wb.stb.eq(1)
                        comb += st_stbs_done.eq(0)

                        with m.If(req.op == Op.OP_STORE_HIT):
                            sync += r1.write_bram.eq(1)
                        sync += r1.full.eq(0)
                        sync += r1.slow_valid.eq(1)

                        # Store requests never come from the MMU
                        sync += r1.ls_valid.eq(1)
                        comb += st_stbs_done.eq(0)
                        sync += r1.inc_acks.eq(1)
                    with m.Else():
                        sync += r1.wb.stb.eq(0)
                        comb += st_stbs_done.eq(1)

                # Got ack ? See if complete.
                with m.If(wb_in.ack):
                    with m.If(st_stbs_done & (adjust_acks == 1)):
                        sync += r1.state.eq(State.IDLE)
                        sync += r1.wb.cyc.eq(0)
                        sync += r1.wb.stb.eq(0)
                    sync += r1.dec_acks.eq(1)

            with m.Case(State.NC_LOAD_WAIT_ACK):
                # Clear stb when slave accepted request
                with m.If(~wb_in.stall):
                    sync += r1.wb.stb.eq(0)

                # Got ack ? complete.
                with m.If(wb_in.ack):
                    sync += r1.state.eq(State.IDLE)
                    sync += r1.full.eq(0)
                    sync += r1.slow_valid.eq(1)

                    with m.If(~r1.mmu_req):
                        sync += r1.ls_valid.eq(1)
                    with m.Else():
                        sync += r1.mmu_done.eq(1)

                    sync += r1.forward_sel.eq(~0) # all 1s
                    sync += r1.use_forward1.eq(1)
                    sync += r1.wb.cyc.eq(0)
                    sync += r1.wb.stb.eq(0)

    def dcache_log(self, m, r1, valid_ra, tlb_hit_way, stall_out):

        sync = m.d.sync
        d_out, wb_in, log_out = self.d_out, self.wb_in, self.log_out

        sync += log_out.eq(Cat(r1.state[:3], valid_ra, tlb_hit_way[:3],
                               stall_out, req_op[:3], d_out.valid, d_out.error,
                               r1.wb.cyc, r1.wb.stb, wb_in.ack, wb_in.stall,
                               r1.real_adr[3:6]))

    def elaborate(self, platform):

        m = Module()
        comb = m.d.comb
        d_in = self.d_in

        # Storage. Hopefully "cache_rows" is a BRAM, the rest is LUTs
        cache_tags       = CacheTagArray()
        cache_tag_set    = Signal(TAG_RAM_WIDTH)
        cache_valids = CacheValidBitsArray()

        # TODO attribute ram_style : string;
        # TODO attribute ram_style of cache_tags : signal is "distributed";

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

        r0      = RegStage0("r0")
        r0_full = Signal()

        r1 = RegStage1("r1")

        reservation = Reservation()

        # Async signals on incoming request
        req_index    = Signal(INDEX_BITS)
        req_row      = Signal(ROW_BITS)
        req_hit_way  = Signal(WAY_BITS)
        req_tag      = Signal(TAG_BITS)
        req_op       = Signal(Op)
        req_data     = Signal(64)
        req_same_tag = Signal()
        req_go       = Signal()

        early_req_row     = Signal(ROW_BITS)

        cancel_store      = Signal()
        set_rsrv          = Signal()
        clear_rsrv        = Signal()

        r0_valid          = Signal()
        r0_stall          = Signal()

        use_forward1_next = Signal()
        use_forward2_next = Signal()

        cache_out_row     = Signal(WB_DATA_BITS)

        plru_victim       = PLRUOut()
        replace_way       = Signal(WAY_BITS)

        # Wishbone read/write/cache write formatting signals
        bus_sel           = Signal(8)

        # TLB signals
        tlb_tag_way   = Signal(TLB_TAG_WAY_BITS)
        tlb_pte_way   = Signal(TLB_PTE_WAY_BITS)
        tlb_valid_way = Signal(TLB_NUM_WAYS)
        tlb_req_index = Signal(TLB_SET_BITS)
        tlb_hit       = Signal()
        tlb_hit_way   = Signal(TLB_WAY_BITS)
        pte           = Signal(TLB_PTE_BITS)
        ra            = Signal(REAL_ADDR_BITS)
        valid_ra      = Signal()
        perm_attr     = PermAttr("dc_perms")
        rc_ok         = Signal()
        perm_ok       = Signal()
        access_ok     = Signal()

        tlb_plru_victim = TLBPLRUOut()

        # we don't yet handle collisions between loadstore1 requests
        # and MMU requests
        comb += self.m_out.stall.eq(0)

        # Hold off the request in r0 when r1 has an uncompleted request
        comb += r0_stall.eq(r0_full & (r1.full | d_in.hold))
        comb += r0_valid.eq(r0_full & ~r1.full & ~d_in.hold)
        comb += self.stall_out.eq(r0_stall)

        # Wire up wishbone request latch out of stage 1
        comb += self.wb_out.eq(r1.wb)

        # deal with litex not doing wishbone pipeline mode
        # XXX in wrong way.  FIFOs are needed in the SRAM test
        # so that stb/ack match up
        comb += self.wb_in.stall.eq(self.wb_out.cyc & ~self.wb_in.ack)

        # call sub-functions putting everything together, using shared
        # signals established above
        self.stage_0(m, r0, r1, r0_full)
        self.tlb_read(m, r0_stall, tlb_valid_way,
                      tlb_tag_way, tlb_pte_way, dtlb_valid_bits,
                      dtlb_tags, dtlb_ptes)
        self.tlb_search(m, tlb_req_index, r0, r0_valid,
                        tlb_valid_way, tlb_tag_way, tlb_hit_way,
                        tlb_pte_way, pte, tlb_hit, valid_ra, perm_attr, ra)
        self.tlb_update(m, r0_valid, r0, dtlb_valid_bits, tlb_req_index,
                        tlb_hit_way, tlb_hit, tlb_plru_victim, tlb_tag_way,
                        dtlb_tags, tlb_pte_way, dtlb_ptes)
        self.maybe_plrus(m, r1, plru_victim)
        self.maybe_tlb_plrus(m, r1, tlb_plru_victim)
        self.cache_tag_read(m, r0_stall, req_index, cache_tag_set, cache_tags)
        self.dcache_request(m, r0, ra, req_index, req_row, req_tag,
                           r0_valid, r1, cache_valids, replace_way,
                           use_forward1_next, use_forward2_next,
                           req_hit_way, plru_victim, rc_ok, perm_attr,
                           valid_ra, perm_ok, access_ok, req_op, req_go,
                           tlb_pte_way,
                           tlb_hit, tlb_hit_way, tlb_valid_way, cache_tag_set,
                           cancel_store, req_same_tag, r0_stall, early_req_row)
        self.reservation_comb(m, cancel_store, set_rsrv, clear_rsrv,
                           r0_valid, r0, reservation)
        self.reservation_reg(m, r0_valid, access_ok, set_rsrv, clear_rsrv,
                           reservation, r0)
        self.writeback_control(m, r1, cache_out_row)
        self.rams(m, r1, early_req_row, cache_out_row, replace_way)
        self.dcache_fast_hit(m, req_op, r0_valid, r0, r1,
                        req_hit_way, req_index, req_tag, access_ok,
                        tlb_hit, tlb_hit_way, tlb_req_index)
        self.dcache_slow(m, r1, use_forward1_next, use_forward2_next,
                    cache_valids, r0, replace_way,
                    req_hit_way, req_same_tag,
                         r0_valid, req_op, cache_tags, req_go, ra)
        #self.dcache_log(m, r1, valid_ra, tlb_hit_way, stall_out)

        return m

def dcache_load(dut, addr, nc=0):
    yield dut.d_in.load.eq(1)
    yield dut.d_in.nc.eq(nc)
    yield dut.d_in.addr.eq(addr)
    yield dut.d_in.byte_sel.eq(~0)
    yield dut.d_in.valid.eq(1)
    yield
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.byte_sel.eq(0)
    while not (yield dut.d_out.valid):
        yield
    # yield # data is valid one cycle AFTER valid goes hi? (no it isn't)
    data = yield dut.d_out.data
    return data


def dcache_store(dut, addr, data, nc=0):
    yield dut.d_in.load.eq(0)
    yield dut.d_in.nc.eq(nc)
    yield dut.d_in.byte_sel.eq(~0)
    yield dut.d_in.addr.eq(addr)
    yield dut.d_in.valid.eq(1)
    yield
    yield dut.d_in.data.eq(data)    # leave set, but the cycle AFTER
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.byte_sel.eq(0)
    while not (yield dut.d_out.valid):
        yield


def dcache_random_sim(dut, mem, nc=0):

    # start copy of mem
    sim_mem = deepcopy(mem)
    memsize = len(sim_mem)
    print ("mem len", memsize)

    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.priv_mode.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield

    print ()

    #for i in range(1024):
    #    sim_mem[i] = i

    for i in range(1024):
        addr = randint(0, memsize-1)
        data = randint(0, (1<<64)-1)
        sim_mem[addr] = data
        row = addr
        addr *= 8

        print ("random testing %d 0x%x row %d data 0x%x" % (i, addr, row, data))

        yield from dcache_load(dut, addr, nc)
        yield from dcache_store(dut, addr, data, nc)

        addr = randint(0, memsize-1)
        sim_data = sim_mem[addr]
        row = addr
        addr *= 8

        print ("    load 0x%x row %d expect data 0x%x" % (addr, row, sim_data))
        data = yield from dcache_load(dut, addr, nc)
        assert data == sim_data, \
            "check addr 0x%x row %d data %x != %x" % (addr, row, data, sim_data)

    for addr in range(memsize):
        data = yield from dcache_load(dut, addr*8, nc)
        assert data == sim_mem[addr], \
            "final check %x data %x != %x" % (addr*8, data, sim_mem[addr])


def dcache_regression_sim(dut, mem, nc=0):

    # start copy of mem
    sim_mem = deepcopy(mem)
    memsize = len(sim_mem)
    print ("mem len", memsize)

    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.priv_mode.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield

    addr = 0
    row = addr
    addr *= 8

    print ("random testing %d 0x%x row %d" % (i, addr, row))

    yield from dcache_load(dut, addr, nc)

    addr = 2
    sim_data = sim_mem[addr]
    row = addr
    addr *= 8

    print ("    load 0x%x row %d expect data 0x%x" % (addr, row, sim_data))
    data = yield from dcache_load(dut, addr, nc)
    assert data == sim_data, \
        "check addr 0x%x row %d data %x != %x" % (addr, row, data, sim_data)



def dcache_sim(dut, mem):
    # clear stuff
    yield dut.d_in.valid.eq(0)
    yield dut.d_in.load.eq(0)
    yield dut.d_in.priv_mode.eq(1)
    yield dut.d_in.nc.eq(0)
    yield dut.d_in.addr.eq(0)
    yield dut.d_in.data.eq(0)
    yield dut.m_in.valid.eq(0)
    yield dut.m_in.addr.eq(0)
    yield dut.m_in.pte.eq(0)
    # wait 4 * clk_period
    yield
    yield
    yield
    yield

    # Cacheable read of address 4
    data = yield from dcache_load(dut, 0x58)
    addr = yield dut.d_in.addr
    assert data == 0x0000001700000016, \
        f"data @%x=%x expected 0x0000001700000016" % (addr, data)

    # Cacheable read of address 20
    data = yield from dcache_load(dut, 0x20)
    addr = yield dut.d_in.addr
    assert data == 0x0000000900000008, \
        f"data @%x=%x expected 0x0000000900000008" % (addr, data)

    # Cacheable read of address 30
    data = yield from dcache_load(dut, 0x530)
    addr = yield dut.d_in.addr
    assert data == 0x0000014D0000014C, \
        f"data @%x=%x expected 0000014D0000014C" % (addr, data)

    # 2nd Cacheable read of address 30
    data = yield from dcache_load(dut, 0x530)
    addr = yield dut.d_in.addr
    assert data == 0x0000014D0000014C, \
        f"data @%x=%x expected 0000014D0000014C" % (addr, data)

    # Non-cacheable read of address 100
    data = yield from dcache_load(dut, 0x100, nc=1)
    addr = yield dut.d_in.addr
    assert data == 0x0000004100000040, \
        f"data @%x=%x expected 0000004100000040" % (addr, data)

    # Store at address 530
    yield from dcache_store(dut, 0x530, 0x121)

    # Store at address 30
    yield from dcache_store(dut, 0x530, 0x12345678)

    # 3nd Cacheable read of address 530
    data = yield from dcache_load(dut, 0x530)
    addr = yield dut.d_in.addr
    assert data == 0x12345678, \
        f"data @%x=%x expected 0x12345678" % (addr, data)

    # 4th Cacheable read of address 20
    data = yield from dcache_load(dut, 0x20)
    addr = yield dut.d_in.addr
    assert data == 0x0000000900000008, \
        f"data @%x=%x expected 0x0000000900000008" % (addr, data)

    yield
    yield
    yield
    yield


def test_dcache(mem, test_fn, test_name):
    dut = DCache()

    memory = Memory(width=64, depth=len(mem), init=mem, simulate=True)
    sram = SRAM(memory=memory, granularity=8)

    m = Module()
    m.submodules.dcache = dut
    m.submodules.sram = sram

    m.d.comb += sram.bus.cyc.eq(dut.wb_out.cyc)
    m.d.comb += sram.bus.stb.eq(dut.wb_out.stb)
    m.d.comb += sram.bus.we.eq(dut.wb_out.we)
    m.d.comb += sram.bus.sel.eq(dut.wb_out.sel)
    m.d.comb += sram.bus.adr.eq(dut.wb_out.adr)
    m.d.comb += sram.bus.dat_w.eq(dut.wb_out.dat)

    m.d.comb += dut.wb_in.ack.eq(sram.bus.ack)
    m.d.comb += dut.wb_in.dat.eq(sram.bus.dat_r)

    dcache_write_gtkw(test_name)

    # nmigen Simulation
    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(test_fn(dut, mem)))
    with sim.write_vcd('test_dcache%s.vcd' % test_name):
        sim.run()


def dcache_write_gtkw(test_name):
    traces = [
        'clk',
        ('d_in', [
            'd_in_load', 'd_in_nc', 'd_in_addr[63:0]', 'd_in_data[63:0]',
            'd_in_byte_sel[7:0]', 'd_in_valid'
        ]),
        ('d_out', [
            'd_out_valid', 'd_out_data[63:0]'
        ]),
        ('wb_out', [
            'wb_out_cyc', 'wb_out_stb', 'wb_out_we',
            'wb_out_adr[31:0]', 'wb_out_sel[7:0]', 'wb_out_dat[63:0]'
        ]),
        ('wb_in', [
            'wb_in_stall', 'wb_in_ack', 'wb_in_dat[63:0]'
        ])
    ]
    write_gtkw('test_dcache%s.gtkw' % test_name,
               'test_dcache%s.vcd' % test_name,
               traces, module='top.dcache')


if __name__ == '__main__':
    seed(0)
    dut = DCache()
    vl = rtlil.convert(dut, ports=[])
    with open("test_dcache.il", "w") as f:
        f.write(vl)

    mem = []
    memsize = 16
    for i in range(memsize):
        mem.append(i)

    test_dcache(mem, dcache_regression_sim, "simpleregression")

    mem = []
    memsize = 256
    for i in range(memsize):
        mem.append(i)

    test_dcache(mem, dcache_random_sim, "random")

    mem = []
    for i in range(1024):
        mem.append((i*2)| ((i*2+1)<<32))

    test_dcache(mem, dcache_sim, "")

