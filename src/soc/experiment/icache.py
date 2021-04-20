"""ICache

based on Anton Blanchard microwatt icache.vhdl

Set associative icache

TODO (in no specific order):
* Add debug interface to inspect cache content
* Add snoop/invalidate path
* Add multi-hit error detection
* Pipelined bus interface (wb or axi)
* Maybe add parity? There's a few bits free in each BRAM row on Xilinx
* Add optimization: service hits on partially loaded lines
* Add optimization: (maybe) interrupt reload on fluch/redirect
* Check if playing with the geometry of the cache tags allow for more
  efficient use of distributed RAM and less logic/muxes. Currently we
  write TAG_BITS width which may not match full ram blocks and might
  cause muxes to be inferred for "partial writes".
* Check if making the read size of PLRU a ROM helps utilization
"""

from enum import (Enum, unique)
from nmigen import (Module, Signal, Elaboratable, Cat, Array, Const, Repl)
from nmigen.cli import main, rtlil
from nmutil.iocontrol import RecordObject
from nmigen.utils import log2_int
from nmutil.util import Display

#from nmutil.plru import PLRU
from soc.experiment.cache_ram import CacheRam
from soc.experiment.plru import PLRU

from soc.experiment.mem_types import (Fetch1ToICacheType,
                                      ICacheToDecode1Type,
                                      MMUToICacheType)

from soc.experiment.wb_types import (WB_ADDR_BITS, WB_DATA_BITS,
                                     WB_SEL_BITS, WBAddrType, WBDataType,
                                     WBSelType, WBMasterOut, WBSlaveOut,
                                     WBMasterOutVector, WBSlaveOutVector,
                                     WBIOMasterOut, WBIOSlaveOut)

# for test
from soc.bus.sram import SRAM
from nmigen import Memory
from nmutil.util import wrap
from nmigen.cli import main, rtlil

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle


SIM            = 0
LINE_SIZE      = 64
# BRAM organisation: We never access more than wishbone_data_bits
# at a time so to save resources we make the array only that wide,
# and use consecutive indices for to make a cache "line"
#
# ROW_SIZE is the width in bytes of the BRAM (based on WB, so 64-bits)
ROW_SIZE       = WB_DATA_BITS // 8
# Number of lines in a set
NUM_LINES      = 16
# Number of ways
NUM_WAYS       = 4
# L1 ITLB number of entries (direct mapped)
TLB_SIZE       = 64
# L1 ITLB log_2(page_size)
TLB_LG_PGSZ    = 12
# Number of real address bits that we store
REAL_ADDR_BITS = 56
# Non-zero to enable log data collection
LOG_LENGTH     = 0

ROW_SIZE_BITS  = ROW_SIZE * 8
# ROW_PER_LINE is the number of row (wishbone) transactions in a line
ROW_PER_LINE   = LINE_SIZE // ROW_SIZE
# BRAM_ROWS is the number of rows in BRAM needed to represent the full icache
BRAM_ROWS      = NUM_LINES * ROW_PER_LINE
# INSN_PER_ROW is the number of 32bit instructions per BRAM row
INSN_PER_ROW   = ROW_SIZE_BITS // 32

# Bit fields counts in the address
#
# INSN_BITS is the number of bits to select an instruction in a row
INSN_BITS      = log2_int(INSN_PER_ROW)
# ROW_BITS is the number of bits to select a row
ROW_BITS       = log2_int(BRAM_ROWS)
# ROW_LINE_BITS is the number of bits to select a row within a line
ROW_LINE_BITS  = log2_int(ROW_PER_LINE)
# LINE_OFF_BITS is the number of bits for the offset in a cache line
LINE_OFF_BITS  = log2_int(LINE_SIZE)
# ROW_OFF_BITS is the number of bits for the offset in a row
ROW_OFF_BITS   = log2_int(ROW_SIZE)
# INDEX_BITS is the number of bits to select a cache line
INDEX_BITS     = log2_int(NUM_LINES)
# SET_SIZE_BITS is the log base 2 of the set size
SET_SIZE_BITS  = LINE_OFF_BITS + INDEX_BITS
# TAG_BITS is the number of bits of the tag part of the address
TAG_BITS       = REAL_ADDR_BITS - SET_SIZE_BITS
# TAG_WIDTH is the width in bits of each way of the tag RAM
TAG_WIDTH      = TAG_BITS + 7 - ((TAG_BITS + 7) % 8)

# WAY_BITS is the number of bits to select a way
WAY_BITS       = log2_int(NUM_WAYS)
TAG_RAM_WIDTH  = TAG_BITS * NUM_WAYS

# L1 ITLB
TLB_BITS        = log2_int(TLB_SIZE)
TLB_EA_TAG_BITS = 64 - (TLB_LG_PGSZ + TLB_BITS)
TLB_PTE_BITS    = 64

print("BRAM_ROWS       =", BRAM_ROWS)
print("INDEX_BITS      =", INDEX_BITS)
print("INSN_BITS       =", INSN_BITS)
print("INSN_PER_ROW    =", INSN_PER_ROW)
print("LINE_SIZE       =", LINE_SIZE)
print("LINE_OFF_BITS   =", LINE_OFF_BITS)
print("LOG_LENGTH      =", LOG_LENGTH)
print("NUM_LINES       =", NUM_LINES)
print("NUM_WAYS        =", NUM_WAYS)
print("REAL_ADDR_BITS  =", REAL_ADDR_BITS)
print("ROW_BITS        =", ROW_BITS)
print("ROW_OFF_BITS    =", ROW_OFF_BITS)
print("ROW_LINE_BITS   =", ROW_LINE_BITS)
print("ROW_PER_LINE    =", ROW_PER_LINE)
print("ROW_SIZE        =", ROW_SIZE)
print("ROW_SIZE_BITS   =", ROW_SIZE_BITS)
print("SET_SIZE_BITS   =", SET_SIZE_BITS)
print("SIM             =", SIM)
print("TAG_BITS        =", TAG_BITS)
print("TAG_RAM_WIDTH   =", TAG_RAM_WIDTH)
print("TAG_BITS        =", TAG_BITS)
print("TLB_BITS        =", TLB_BITS)
print("TLB_EA_TAG_BITS =", TLB_EA_TAG_BITS)
print("TLB_LG_PGSZ     =", TLB_LG_PGSZ)
print("TLB_PTE_BITS    =", TLB_PTE_BITS)
print("TLB_SIZE        =", TLB_SIZE)
print("WAY_BITS        =", WAY_BITS)

# from microwatt/utils.vhdl
def ispow2(n):
    return n != 0 and (n & (n - 1)) == 0

assert LINE_SIZE % ROW_SIZE == 0
assert ispow2(LINE_SIZE), "LINE_SIZE not power of 2"
assert ispow2(NUM_LINES), "NUM_LINES not power of 2"
assert ispow2(ROW_PER_LINE), "ROW_PER_LINE not power of 2"
assert ispow2(INSN_PER_ROW), "INSN_PER_ROW not power of 2"
assert (ROW_BITS == (INDEX_BITS + ROW_LINE_BITS)), \
    "geometry bits don't add up"
assert (LINE_OFF_BITS == (ROW_OFF_BITS + ROW_LINE_BITS)), \
   "geometry bits don't add up"
assert (REAL_ADDR_BITS == (TAG_BITS + INDEX_BITS + LINE_OFF_BITS)), \
    "geometry bits don't add up"
assert (REAL_ADDR_BITS == (TAG_BITS + ROW_BITS + ROW_OFF_BITS)), \
    "geometry bits don't add up"

# Example of layout for 32 lines of 64 bytes:
#
# ..  tag    |index|  line  |
# ..         |   row   |    |
# ..         |     |   | |00| zero          (2)
# ..         |     |   |-|  | INSN_BITS     (1)
# ..         |     |---|    | ROW_LINE_BITS  (3)
# ..         |     |--- - --| LINE_OFF_BITS (6)
# ..         |         |- --| ROW_OFF_BITS  (3)
# ..         |----- ---|    | ROW_BITS      (8)
# ..         |-----|        | INDEX_BITS    (5)
# .. --------|              | TAG_BITS      (53)

# The cache data BRAM organized as described above for each way
#subtype cache_row_t is std_ulogic_vector(ROW_SIZE_BITS-1 downto 0);
#
# The cache tags LUTRAM has a row per set. Vivado is a pain and will
# not handle a clean (commented) definition of the cache tags as a 3d
# memory. For now, work around it by putting all the tags
def CacheTagArray():
    return Array(Signal(TAG_RAM_WIDTH, name="cachetag_%d" %x) \
                 for x in range(NUM_LINES))

# The cache valid bits
def CacheValidBitsArray():
    return Array(Signal(NUM_WAYS, name="cachevalid_%d" %x) \
                 for x in range(NUM_LINES))

def RowPerLineValidArray():
    return Array(Signal(name="rows_valid_%d" %x) \
                 for x in range(ROW_PER_LINE))


# TODO to be passed to nigmen as ram attributes
# attribute ram_style : string;
# attribute ram_style of cache_tags : signal is "distributed";


def TLBValidBitsArray():
    return Array(Signal(name="tlbvalid_%d" %x) \
                 for x in range(TLB_SIZE))

def TLBTagArray():
    return Array(Signal(TLB_EA_TAG_BITS, name="tlbtag_%d" %x) \
                 for x in range(TLB_SIZE))

def TLBPtesArray():
    return Array(Signal(TLB_PTE_BITS, name="tlbptes_%d" %x) \
                 for x in range(TLB_SIZE))

# Cache RAM interface
def CacheRamOut():
    return Array(Signal(ROW_SIZE_BITS, name="cache_out_%d" %x) \
                 for x in range(NUM_WAYS))

# PLRU output interface
def PLRUOut():
    return Array(Signal(WAY_BITS, name="plru_out_%d" %x) \
                 for x in range(NUM_LINES))

# Return the cache line index (tag index) for an address
def get_index(addr):
    return addr[LINE_OFF_BITS:SET_SIZE_BITS]

# Return the cache row index (data memory) for an address
def get_row(addr):
    return addr[ROW_OFF_BITS:SET_SIZE_BITS]

# Return the index of a row within a line
def get_row_of_line(row):
    return row[:ROW_LINE_BITS]

# Returns whether this is the last row of a line
def is_last_row_addr(addr, last):
    return addr[ROW_OFF_BITS:LINE_OFF_BITS] == last

# Returns whether this is the last row of a line
def is_last_row(row, last):
    return get_row_of_line(row) == last

# Return the next row in the current cache line. We use a dedicated
# function in order to limit the size of the generated adder to be
# only the bits within a cache line (3 bits with default settings)
def next_row(row):
    row_v = row[0:ROW_LINE_BITS] + 1
    return Cat(row_v[:ROW_LINE_BITS], row[ROW_LINE_BITS:])

# Read the instruction word for the given address
# in the current cache row
def read_insn_word(addr, data):
    word = addr[2:INSN_BITS+2]
    return data.word_select(word, 32)

# Get the tag value from the address
def get_tag(addr):
    return addr[SET_SIZE_BITS:REAL_ADDR_BITS]

# Read a tag from a tag memory row
def read_tag(way, tagset):
    return tagset.word_select(way, TAG_BITS)

# Write a tag to tag memory row
def write_tag(way, tagset, tag):
    return read_tag(way, tagset).eq(tag)

# Simple hash for direct-mapped TLB index
def hash_ea(addr):
    hsh = addr[TLB_LG_PGSZ:TLB_LG_PGSZ + TLB_BITS] ^ addr[
           TLB_LG_PGSZ + TLB_BITS:TLB_LG_PGSZ + 2 * TLB_BITS
          ] ^ addr[
           TLB_LG_PGSZ + 2 * TLB_BITS:TLB_LG_PGSZ + 3 * TLB_BITS
          ]
    return hsh


# Cache reload state machine
@unique
class State(Enum):
    IDLE     = 0
    CLR_TAG  = 1
    WAIT_ACK = 2


class RegInternal(RecordObject):
    def __init__(self):
        super().__init__()
        # Cache hit state (Latches for 1 cycle BRAM access)
        self.hit_way      = Signal(NUM_WAYS)
        self.hit_nia      = Signal(64)
        self.hit_smark    = Signal()
        self.hit_valid    = Signal()

        # Cache miss state (reload state machine)
        self.state        = Signal(State, reset=State.IDLE)
        self.wb           = WBMasterOut("wb")
        self.req_adr      = Signal(64)
        self.store_way    = Signal(NUM_WAYS)
        self.store_index  = Signal(NUM_LINES)
        self.store_row    = Signal(BRAM_ROWS)
        self.store_tag    = Signal(TAG_BITS)
        self.store_valid  = Signal()
        self.end_row_ix   = Signal(ROW_LINE_BITS)
        self.rows_valid   = RowPerLineValidArray()

        # TLB miss state
        self.fetch_failed = Signal()


class ICache(Elaboratable):
    """64 bit direct mapped icache. All instructions are 4B aligned."""
    def __init__(self):
        self.i_in           = Fetch1ToICacheType(name="i_in")
        self.i_out          = ICacheToDecode1Type(name="i_out")

        self.m_in           = MMUToICacheType(name="m_in")

        self.stall_in       = Signal()
        self.stall_out      = Signal()
        self.flush_in       = Signal()
        self.inval_in       = Signal()

        self.wb_out         = WBMasterOut(name="wb_out")
        self.wb_in          = WBSlaveOut(name="wb_in")

        self.log_out        = Signal(54)


    # Generate a cache RAM for each way
    def rams(self, m, r, cache_out_row, use_previous,
             replace_way, req_row):

        comb = m.d.comb
        sync = m.d.sync

        wb_in, stall_in = self.wb_in, self.stall_in

        for i in range(NUM_WAYS):
            do_read  = Signal(name="do_rd_%d" % i)
            do_write = Signal(name="do_wr_%d" % i)
            rd_addr  = Signal(ROW_BITS)
            wr_addr  = Signal(ROW_BITS)
            d_out    = Signal(ROW_SIZE_BITS, name="d_out_%d" % i)
            wr_sel   = Signal(ROW_SIZE)

            way = CacheRam(ROW_BITS, ROW_SIZE_BITS, True)
            setattr(m.submodules, "cacheram_%d" % i, way)

            comb += way.rd_en.eq(do_read)
            comb += way.rd_addr.eq(rd_addr)
            comb += d_out.eq(way.rd_data_o)
            comb += way.wr_sel.eq(wr_sel)
            comb += way.wr_addr.eq(wr_addr)
            comb += way.wr_data.eq(wb_in.dat)

            comb += do_read.eq(~(stall_in | use_previous))
            comb += do_write.eq(wb_in.ack & (replace_way == i))

            with m.If(do_write):
                sync += Display("cache write adr: %x data: %lx",
                                wr_addr, way.wr_data)

            with m.If(r.hit_way == i):
                comb += cache_out_row.eq(d_out)
                with m.If(do_read):
                    sync += Display("cache read adr: %x data: %x",
                                     req_row, d_out)

            comb += rd_addr.eq(req_row)
            comb += wr_addr.eq(r.store_row)
            comb += wr_sel.eq(Repl(do_write, ROW_SIZE))

    # Generate PLRUs
    def maybe_plrus(self, m, r, plru_victim):
        comb = m.d.comb

        with m.If(NUM_WAYS > 1):
            for i in range(NUM_LINES):
                plru_acc_i  = Signal(WAY_BITS)
                plru_acc_en = Signal()
                plru        = PLRU(WAY_BITS)
                setattr(m.submodules, "plru_%d" % i, plru)

                comb += plru.acc_i.eq(plru_acc_i)
                comb += plru.acc_en.eq(plru_acc_en)

                # PLRU interface
                with m.If(get_index(r.hit_nia) == i):
                    comb += plru.acc_en.eq(r.hit_valid)

                comb += plru.acc_i.eq(r.hit_way)
                comb += plru_victim[i].eq(plru.lru_o)

    # TLB hit detection and real address generation
    def itlb_lookup(self, m, tlb_req_index, itlb_ptes, itlb_tags,
                    real_addr, itlb_valid_bits, ra_valid, eaa_priv,
                    priv_fault, access_ok):

        comb = m.d.comb

        i_in = self.i_in

        pte  = Signal(TLB_PTE_BITS)
        ttag = Signal(TLB_EA_TAG_BITS)

        comb += tlb_req_index.eq(hash_ea(i_in.nia))
        comb += pte.eq(itlb_ptes[tlb_req_index])
        comb += ttag.eq(itlb_tags[tlb_req_index])

        with m.If(i_in.virt_mode):
            comb += real_addr.eq(Cat(
                     i_in.nia[:TLB_LG_PGSZ],
                     pte[TLB_LG_PGSZ:REAL_ADDR_BITS]
                    ))

            with m.If(ttag == i_in.nia[TLB_LG_PGSZ + TLB_BITS:64]):
                comb += ra_valid.eq(itlb_valid_bits[tlb_req_index])

            comb += eaa_priv.eq(pte[3])

        with m.Else():
            comb += real_addr.eq(i_in.nia[:REAL_ADDR_BITS])
            comb += ra_valid.eq(1)
            comb += eaa_priv.eq(1)

        # No IAMR, so no KUEP support for now
        comb += priv_fault.eq(eaa_priv & ~i_in.priv_mode)
        comb += access_ok.eq(ra_valid & ~priv_fault)

    # iTLB update
    def itlb_update(self, m, itlb_valid_bits, itlb_tags, itlb_ptes):
        comb = m.d.comb
        sync = m.d.sync

        m_in = self.m_in

        wr_index = Signal(TLB_SIZE)
        comb += wr_index.eq(hash_ea(m_in.addr))

        with m.If(m_in.tlbie & m_in.doall):
            # Clear all valid bits
            for i in range(TLB_SIZE):
                sync += itlb_valid_bits[i].eq(0)

        with m.Elif(m_in.tlbie):
            # Clear entry regardless of hit or miss
            sync += itlb_valid_bits[wr_index].eq(0)

        with m.Elif(m_in.tlbld):
            sync += itlb_tags[wr_index].eq(
                     m_in.addr[TLB_LG_PGSZ + TLB_BITS:64]
                    )
            sync += itlb_ptes[wr_index].eq(m_in.pte)
            sync += itlb_valid_bits[wr_index].eq(1)

    # Cache hit detection, output to fetch2 and other misc logic
    def icache_comb(self, m, use_previous, r, req_index, req_row,
                    req_hit_way, req_tag, real_addr, req_laddr,
                    cache_valid_bits, cache_tags, access_ok,
                    req_is_hit, req_is_miss, replace_way,
                    plru_victim, cache_out_row):

        comb = m.d.comb

        i_in, i_out, wb_out = self.i_in, self.i_out, self.wb_out
        flush_in, stall_out = self.flush_in, self.stall_out

        is_hit  = Signal()
        hit_way = Signal(NUM_WAYS)

        # i_in.sequential means that i_in.nia this cycle is 4 more than
        # last cycle.  If we read more than 32 bits at a time, had a
        # cache hit last cycle, and we don't want the first 32-bit chunk
        # then we can keep the data we read last cycle and just use that.
        with m.If(i_in.nia[2:INSN_BITS+2] != 0):
            comb += use_previous.eq(i_in.sequential & r.hit_valid)

        # Extract line, row and tag from request
        comb += req_index.eq(get_index(i_in.nia))
        comb += req_row.eq(get_row(i_in.nia))
        comb += req_tag.eq(get_tag(real_addr))

        # Calculate address of beginning of cache row, will be
        # used for cache miss processing if needed
        comb += req_laddr.eq(Cat(
                 Const(0, ROW_OFF_BITS),
                 real_addr[ROW_OFF_BITS:REAL_ADDR_BITS],
                ))

        # Test if pending request is a hit on any way
        hitcond = Signal()
        comb += hitcond.eq((r.state == State.WAIT_ACK)
                 & (req_index == r.store_index)
                 & r.rows_valid[req_row % ROW_PER_LINE]
                )
        with m.If(i_in.req):
            cvb = Signal(NUM_WAYS)
            ctag = Signal(TAG_RAM_WIDTH)
            comb += ctag.eq(cache_tags[req_index])
            comb += cvb.eq(cache_valid_bits[req_index])
            for i in range(NUM_WAYS):
                tagi = Signal(TAG_BITS, name="tag_i%d" % i)
                comb += tagi.eq(read_tag(i, ctag))
                hit_test = Signal(name="hit_test%d" % i)
                comb += hit_test.eq(i == r.store_way)
                with m.If((cvb[i] | (hitcond & hit_test))
                          & (tagi == req_tag)):
                    comb += hit_way.eq(i)
                    comb += is_hit.eq(1)

        # Generate the "hit" and "miss" signals
        # for the synchronous blocks
        with m.If(i_in.req & access_ok & ~flush_in):
            comb += req_is_hit.eq(is_hit)
            comb += req_is_miss.eq(~is_hit)

        with m.Else():
            comb += req_is_hit.eq(0)
            comb += req_is_miss.eq(0)

        comb += req_hit_way.eq(hit_way)

        # The way to replace on a miss
        with m.If(r.state == State.CLR_TAG):
            comb += replace_way.eq(plru_victim[r.store_index])
        with m.Else():
            comb += replace_way.eq(r.store_way)

        # Output instruction from current cache row
        #
        # Note: This is a mild violation of our design principle of
        # having pipeline stages output from a clean latch. In this
        # case we output the result of a mux. The alternative would
        # be output an entire row which I prefer not to do just yet
        # as it would force fetch2 to know about some of the cache
        # geometry information.
        comb += i_out.insn.eq(read_insn_word(r.hit_nia, cache_out_row))
        comb += i_out.valid.eq(r.hit_valid)
        comb += i_out.nia.eq(r.hit_nia)
        comb += i_out.stop_mark.eq(r.hit_smark)
        comb += i_out.fetch_failed.eq(r.fetch_failed)

        # Stall fetch1 if we have a miss on cache or TLB
        # or a protection fault
        comb += stall_out.eq(~(is_hit & access_ok))

        # Wishbone requests output (from the cache miss reload machine)
        comb += wb_out.eq(r.wb)

    # Cache hit synchronous machine
    def icache_hit(self, m, use_previous, r, req_is_hit, req_hit_way,
                   req_index, req_tag, real_addr):
        sync = m.d.sync

        i_in, stall_in = self.i_in, self.stall_in
        flush_in       = self.flush_in

        # keep outputs to fetch2 unchanged on a stall
        # except that flush or reset sets valid to 0
        # If use_previous, keep the same data as last
        # cycle and use the second half
        with m.If(stall_in | use_previous):
            with m.If(flush_in):
                sync += r.hit_valid.eq(0)
        with m.Else():
            # On a hit, latch the request for the next cycle,
            # when the BRAM data will be available on the
            # cache_out output of the corresponding way
            sync += r.hit_valid.eq(req_is_hit)

            with m.If(req_is_hit):
                sync += r.hit_way.eq(req_hit_way)
                sync += Display(
                         "cache hit nia:%x IR:%x SM:%x idx:%x tag:%x " \
                         "way:%x RA:%x", i_in.nia, i_in.virt_mode, \
                         i_in.stop_mark, req_index, req_tag, \
                         req_hit_way, real_addr
                        )



        with m.If(~stall_in):
            # Send stop marks and NIA down regardless of validity
            sync += r.hit_smark.eq(i_in.stop_mark)
            sync += r.hit_nia.eq(i_in.nia)

    def icache_miss_idle(self, m, r, req_is_miss, req_laddr,
                         req_index, req_tag, replace_way, real_addr):
        comb = m.d.comb
        sync = m.d.sync

        i_in = self.i_in

        # Reset per-row valid flags, only used in WAIT_ACK
        for i in range(ROW_PER_LINE):
            sync += r.rows_valid[i].eq(0)

        # We need to read a cache line
        with m.If(req_is_miss):
            sync += Display(
                     "cache miss nia:%x IR:%x SM:%x idx:%x "
                     " way:%x tag:%x RA:%x", i_in.nia,
                     i_in.virt_mode, i_in.stop_mark, req_index,
                     replace_way, req_tag, real_addr
                    )

            # Keep track of our index and way for subsequent stores
            st_row = Signal(BRAM_ROWS)
            comb += st_row.eq(get_row(req_laddr))
            sync += r.store_index.eq(req_index)
            sync += r.store_row.eq(st_row)
            sync += r.store_tag.eq(req_tag)
            sync += r.store_valid.eq(1)
            sync += r.end_row_ix.eq(get_row_of_line(st_row) - 1)

            # Prep for first wishbone read.  We calculate the address
            # of the start of the cache line and start the WB cycle.
            sync += r.req_adr.eq(req_laddr)
            sync += r.wb.cyc.eq(1)
            sync += r.wb.stb.eq(1)

            # Track that we had one request sent
            sync += r.state.eq(State.CLR_TAG)

    def icache_miss_clr_tag(self, m, r, replace_way,
                            cache_valid_bits, req_index,
                            tagset, cache_tags):

        comb = m.d.comb
        sync = m.d.sync

        # Get victim way from plru
        sync += r.store_way.eq(replace_way)
        # Force misses on that way while reloading that line
        cv = Signal(INDEX_BITS)
        comb += cv.eq(cache_valid_bits[req_index])
        comb += cv.bit_select(replace_way, 1).eq(0)
        sync += cache_valid_bits[req_index].eq(cv)

        for i in range(NUM_WAYS):
            with m.If(i == replace_way):
                comb += tagset.eq(cache_tags[r.store_index])
                comb += write_tag(i, tagset, r.store_tag)
                sync += cache_tags[r.store_index].eq(tagset)

        sync += r.state.eq(State.WAIT_ACK)

    def icache_miss_wait_ack(self, m, r, replace_way, inval_in,
                             stbs_done, cache_valid_bits):
        comb = m.d.comb
        sync = m.d.sync

        wb_in = self.wb_in

        # Requests are all sent if stb is 0
        stbs_zero = Signal()
        comb += stbs_zero.eq(r.wb.stb == 0)
        comb += stbs_done.eq(stbs_zero)

        # If we are still sending requests, was one accepted?
        with m.If(~wb_in.stall & ~stbs_zero):
            # That was the last word? We are done sending.
            # Clear stb and set stbs_done so we can handle
            # an eventual last ack on the same cycle.
            with m.If(is_last_row_addr(r.req_adr, r.end_row_ix)):
                sync += Display(
                         "IS_LAST_ROW_ADDR r.wb.addr:%x " \
                         "r.end_row_ix:%x r.wb.stb:%x stbs_zero:%x " \
                         "stbs_done:%x", r.wb.adr, r.end_row_ix,
                         r.wb.stb, stbs_zero, stbs_done
                        )
                sync += r.wb.stb.eq(0)
                comb += stbs_done.eq(1)

            # Calculate the next row address
            rarange = Signal(LINE_OFF_BITS - ROW_OFF_BITS)
            comb += rarange.eq(
                     r.req_adr[ROW_OFF_BITS:LINE_OFF_BITS] + 1
                    )
            sync += r.req_adr[ROW_OFF_BITS:LINE_OFF_BITS].eq(
                     rarange
                    )
            sync += Display("RARANGE r.req_adr:%x rarange:%x "
                            "stbs_zero:%x stbs_done:%x",
                            r.req_adr, rarange, stbs_zero, stbs_done)

        # Incoming acks processing
        with m.If(wb_in.ack):
            sync += Display("WB_IN_ACK data:%x stbs_zero:%x "
                            "stbs_done:%x",
                            wb_in.dat, stbs_zero, stbs_done)

            sync += r.rows_valid[r.store_row % ROW_PER_LINE].eq(1)

            # Check for completion
            with m.If(stbs_done &
                      is_last_row(r.store_row, r.end_row_ix)):
                # Complete wishbone cycle
                sync += r.wb.cyc.eq(0)
                # be nice, clear addr
                sync += r.req_adr.eq(0)

                # Cache line is now valid
                cv = Signal(INDEX_BITS)
                comb += cv.eq(cache_valid_bits[r.store_index])
                comb += cv.bit_select(replace_way, 1).eq(
                         r.store_valid & ~inval_in
                        )
                sync += cache_valid_bits[r.store_index].eq(cv)

                sync += r.state.eq(State.IDLE)

            # not completed, move on to next request in row
            with m.Else():
                # Increment store row counter
                sync += r.store_row.eq(next_row(r.store_row))


    # Cache miss/reload synchronous machine
    def icache_miss(self, m, cache_valid_bits, r, req_is_miss,
                    req_index, req_laddr, req_tag, replace_way,
                    cache_tags, access_ok, real_addr):
        comb = m.d.comb
        sync = m.d.sync

        i_in, wb_in, m_in  = self.i_in, self.wb_in, self.m_in
        stall_in, flush_in = self.stall_in, self.flush_in
        inval_in           = self.inval_in

        tagset    = Signal(TAG_RAM_WIDTH)
        stbs_done = Signal()

        comb += r.wb.sel.eq(-1)
        comb += r.wb.adr.eq(r.req_adr[3:])

        # Process cache invalidations
        with m.If(inval_in):
            for i in range(NUM_LINES):
                sync += cache_valid_bits[i].eq(0)
            sync += r.store_valid.eq(0)

        # Main state machine
        with m.Switch(r.state):

            with m.Case(State.IDLE):
                self.icache_miss_idle(
                    m, r, req_is_miss, req_laddr,
                    req_index, req_tag, replace_way,
                    real_addr
                )

            with m.Case(State.CLR_TAG, State.WAIT_ACK):
                with m.If(r.state == State.CLR_TAG):
                    self.icache_miss_clr_tag(
                        m, r, replace_way,
                        cache_valid_bits, req_index,
                        tagset, cache_tags
                    )

                self.icache_miss_wait_ack(
                    m, r, replace_way, inval_in,
                    stbs_done, cache_valid_bits
                )

        # TLB miss and protection fault processing
        with m.If(flush_in | m_in.tlbld):
            sync += r.fetch_failed.eq(0)
        with m.Elif(i_in.req & ~access_ok & ~stall_in):
            sync += r.fetch_failed.eq(1)

    # icache_log: if LOG_LENGTH > 0 generate
    def icache_log(self, m, req_hit_way, ra_valid, access_ok,
                   req_is_miss, req_is_hit, lway, wstate, r):
        comb = m.d.comb
        sync = m.d.sync

        wb_in, i_out       = self.wb_in, self.i_out
        log_out, stall_out = self.log_out, self.stall_out

        # Output data to logger
        for i in range(LOG_LENGTH):
            log_data = Signal(54)
            lway     = Signal(NUM_WAYS)
            wstate   = Signal()

            sync += lway.eq(req_hit_way)
            sync += wstate.eq(0)

            with m.If(r.state != State.IDLE):
                sync += wstate.eq(1)

            sync += log_data.eq(Cat(
                     ra_valid, access_ok, req_is_miss, req_is_hit,
                     lway, wstate, r.hit_nia[2:6], r.fetch_failed,
                     stall_out, wb_in.stall, r.wb.cyc, r.wb.stb,
                     r.real_addr[3:6], wb_in.ack, i_out.insn, i_out.valid
                    ))
            comb += log_out.eq(log_data)

    def elaborate(self, platform):

        m                = Module()
        comb             = m.d.comb

        # Storage. Hopefully "cache_rows" is a BRAM, the rest is LUTs
        cache_tags       = CacheTagArray()
        cache_valid_bits = CacheValidBitsArray()

        itlb_valid_bits  = TLBValidBitsArray()
        itlb_tags        = TLBTagArray()
        itlb_ptes        = TLBPtesArray()
        # TODO to be passed to nmigen as ram attributes
        # attribute ram_style of itlb_tags : signal is "distributed";
        # attribute ram_style of itlb_ptes : signal is "distributed";

        # Privilege bit from PTE EAA field
        eaa_priv         = Signal()

        r                = RegInternal()

        # Async signal on incoming request
        req_index        = Signal(NUM_LINES)
        req_row          = Signal(BRAM_ROWS)
        req_hit_way      = Signal(NUM_WAYS)
        req_tag          = Signal(TAG_BITS)
        req_is_hit       = Signal()
        req_is_miss      = Signal()
        req_laddr        = Signal(64)

        tlb_req_index    = Signal(TLB_SIZE)
        real_addr        = Signal(REAL_ADDR_BITS)
        ra_valid         = Signal()
        priv_fault       = Signal()
        access_ok        = Signal()
        use_previous     = Signal()

        cache_out_row    = Signal(ROW_SIZE_BITS)

        plru_victim      = PLRUOut()
        replace_way      = Signal(NUM_WAYS)

        # call sub-functions putting everything together,
        # using shared signals established above
        self.rams(m, r, cache_out_row, use_previous, replace_way, req_row)
        self.maybe_plrus(m, r, plru_victim)
        self.itlb_lookup(m, tlb_req_index, itlb_ptes, itlb_tags, real_addr,
                         itlb_valid_bits, ra_valid, eaa_priv, priv_fault,
                         access_ok)
        self.itlb_update(m, itlb_valid_bits, itlb_tags, itlb_ptes)
        self.icache_comb(m, use_previous, r, req_index, req_row, req_hit_way,
                         req_tag, real_addr, req_laddr, cache_valid_bits,
                         cache_tags, access_ok, req_is_hit, req_is_miss,
                         replace_way, plru_victim, cache_out_row)
        self.icache_hit(m, use_previous, r, req_is_hit, req_hit_way,
                        req_index, req_tag, real_addr)
        self.icache_miss(m, cache_valid_bits, r, req_is_miss, req_index,
                         req_laddr, req_tag, replace_way, cache_tags,
                         access_ok, real_addr)
        #self.icache_log(m, log_out, req_hit_way, ra_valid, access_ok,
        #                req_is_miss, req_is_hit, lway, wstate, r)

        return m


def icache_sim(dut):
    i_out = dut.i_in
    i_in  = dut.i_out
    m_out = dut.m_in

    yield i_in.valid.eq(0)
    yield i_out.priv_mode.eq(1)
    yield i_out.req.eq(0)
    yield i_out.nia.eq(0)
    yield i_out.stop_mark.eq(0)
    yield m_out.tlbld.eq(0)
    yield m_out.tlbie.eq(0)
    yield m_out.addr.eq(0)
    yield m_out.pte.eq(0)
    yield
    yield
    yield
    yield
    yield i_out.req.eq(1)
    yield i_out.nia.eq(Const(0x0000000000000004, 64))
    for i in range(30):
        yield
    yield
    valid = yield i_in.valid
    nia   = yield i_out.nia
    insn  = yield i_in.insn
    print(f"valid? {valid}")
    assert valid
    assert insn == 0x00000001, \
        "insn @%x=%x expected 00000001" % (nia, insn)
    yield i_out.req.eq(0)
    yield

    # hit
    yield
    yield
    yield i_out.req.eq(1)
    yield i_out.nia.eq(Const(0x0000000000000008, 64))
    yield
    yield
    valid = yield i_in.valid
    nia   = yield i_in.nia
    insn  = yield i_in.insn
    assert valid
    assert insn == 0x00000002, \
        "insn @%x=%x expected 00000002" % (nia, insn)
    yield

    # another miss
    yield i_out.req.eq(1)
    yield i_out.nia.eq(Const(0x0000000000000040, 64))
    for i in range(30):
        yield
    yield
    valid = yield i_in.valid
    nia   = yield i_out.nia
    insn  = yield i_in.insn
    assert valid
    assert insn == 0x00000010, \
        "insn @%x=%x expected 00000010" % (nia, insn)

    # test something that aliases
    yield i_out.req.eq(1)
    yield i_out.nia.eq(Const(0x0000000000000100, 64))
    yield
    yield
    valid = yield i_in.valid
    assert ~valid
    for i in range(30):
        yield
    yield
    insn  = yield i_in.insn
    valid = yield i_in.valid
    insn  = yield i_in.insn
    assert valid
    assert insn == 0x00000040, \
         "insn @%x=%x expected 00000040" % (nia, insn)
    yield i_out.req.eq(0)



def test_icache(mem):
     dut    = ICache()

     memory = Memory(width=64, depth=512, init=mem)
     sram   = SRAM(memory=memory, granularity=8)

     m      = Module()

     m.submodules.icache = dut
     m.submodules.sram   = sram

     m.d.comb += sram.bus.cyc.eq(dut.wb_out.cyc)
     m.d.comb += sram.bus.stb.eq(dut.wb_out.stb)
     m.d.comb += sram.bus.we.eq(dut.wb_out.we)
     m.d.comb += sram.bus.sel.eq(dut.wb_out.sel)
     m.d.comb += sram.bus.adr.eq(dut.wb_out.adr)
     m.d.comb += sram.bus.dat_w.eq(dut.wb_out.dat)

     m.d.comb += dut.wb_in.ack.eq(sram.bus.ack)
     m.d.comb += dut.wb_in.dat.eq(sram.bus.dat_r)

     # nmigen Simulation
     sim = Simulator(m)
     sim.add_clock(1e-6)

     sim.add_sync_process(wrap(icache_sim(dut)))
     with sim.write_vcd('test_icache.vcd'):
         sim.run()

if __name__ == '__main__':
    dut = ICache()
    vl = rtlil.convert(dut, ports=[])
    with open("test_icache.il", "w") as f:
        f.write(vl)

    mem = []
    for i in range(512):
        mem.append((i*2) | ((i*2+1)<<32))

    test_icache(mem)

