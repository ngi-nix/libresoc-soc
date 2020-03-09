# Copyright 2018 ETH Zurich and University of Bologna.
# Copyright and related rights are licensed under the Solderpad Hardware
# License, Version 0.51 (the "License"); you may not use this file except in
# compliance with the License.  You may obtain a copy of the License at
# http:#solderpad.org/licenses/SHL-0.51. Unless required by applicable law
# or agreed to in writing, software, hardware and materials distributed under
# this License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#
# Author: Florian Zaruba, ETH Zurich
# Date: 12.11.2017
# Description: Handles cache misses.
from nmigen.lib.coding import Encoder, PriorityEncoder


# --------------
# MISS Handler
# --------------
import ariane_pkg::*;
import std_cache_pkg::*;

unsigned NR_PORTS         = 3

class MissReq(RecordObject):
    def __init__(self, name=None):
        Record.__init__(self, name)
        self.valid = Signal()
        self.addr = Signal(64)
        self.be = Signal(8)
        self.size = Signal(2)
        self.we = Signal()
        self.wdata = Signal(64)
        bypass = Signal()

class CacheLine:
    def __init__(self):
        self.tag = Signal(DCACHE_TAG_WIDTH) # tag array
        self.data = Signal(DCACHE_LINE_WIDTH) # data array
        self.valid = Signal() # state array
        self.dirty = Signal() # state array

# cache line byte enable
class CLBE:
    def __init__(self):
        self.tag = Signal(DCACHE_TAG_WIDTH+7)//8) # byte enable into tag array
        self.data = Signal(DCACHE_LINE_WIDTH+7)//8) # byte enable data array
        # bit enable into state array (valid for a pair of dirty/valid bits)
        self.vldrty = Signal(DCACHE_SET_ASSOC)
    } cl_be_t;



    # FSM states
"""
    enum logic [3:0] {
        IDLE,               # 0
        FLUSHING,           # 1
        FLUSH,              # 2
        WB_CACHELINE_FLUSH, # 3
        FLUSH_REQ_STATUS,   # 4
        WB_CACHELINE_MISS,  # 5
        WAIT_GNT_SRAM,      # 6
        MISS,               # 7
        REQ_CACHELINE,      # 8
        MISS_REPL,          # 9
        SAVE_CACHELINE,     # A
        INIT,               # B
        AMO_LOAD,           # C
        AMO_SAVE_LOAD,      # D
        AMO_STORE           # E
    } state_d, state_q;
"""

class MissHandler(Elaboratable):
    def __init__(self, NR_PORTS):
        self.NR_PORTS = NR_PORTS
        self.pwid = pwid = ceil(log(NR_PORTS) / log(2))
        self.flush_i = Signal()      # flush request
        self.flush_ack_o = Signal()  # acknowledge successful flush
        self.miss_o = Signal()
        self.busy_i = Signal()       # dcache is busy with something

        # Bypass or miss
        self.miss_req_i = Array(MissReq(name="missreq") for i in range(NR_PORTS))
        # Bypass handling
        self.bypass_gnt_o = Signal(NR_PORTS)
        self.bypass_valid_o = Signal(NR_PORTS)
        self.bypass_data_o = Array(Signal(name="bdata_o", 64) \
                                    for i in range(NR_PORTS))

        # AXI port
        output ariane_axi::req_t                            axi_bypass_o,
        input  ariane_axi::resp_t                           axi_bypass_i,

        # Miss handling (~> cacheline refill)
        self.miss_gnt_o = Signal(NR_PORTS)
        self.active_serving_o = Signal(NR_PORTS)

        self.critical_word_o = Signal(64)
        self.critical_word_valid_o = Signal()
        output ariane_axi::req_t                            axi_data_o,
        input  ariane_axi::resp_t                           axi_data_i,

        self.mshr_addr_i = Array(Signal(name="bdata_o", 56) \
                                    for i in range(NR_PORTS))
        self.mshr_addr_matches_o = Signal(NR_PORTS)
        self.mshr_index_matches_o = Signal(NR_PORTS)

        # AMO
        self.amo_req_i = AMOReq()
        self.amo_resp_o = AMOResp()
        # Port to SRAMs, for refill and eviction
        self.req_o = Signal(DCACHE_SET_ASSOC)
        self.addr_o = Signal(DCACHE_INDEX_WIDTH) # address into cache array
        self.data_o = CacheLine()
        self.be_o = CLBE()
        self.data_i = Array(CacheLine() \
                                    for i in range(DCACHE_SET_ASSOC))
        self.we_o = Signal()

    def elaborate(self, platform):
        # Registers
        mshr_t                                  mshr_d, mshr_q;
        logic [DCACHE_INDEX_WIDTH-1:0]          cnt_d, cnt_q;
        logic [DCACHE_SET_ASSOC-1:0]            evict_way_d, evict_way_q;
        # cache line to evict
        cache_line_t                            evict_cl_d, evict_cl_q;

        logic serve_amo_d, serve_amo_q;
        # Request from one FSM
        miss_req_valid = Signal(self.NR_PORTS)
        miss_req_bypass = Signal(self.NR_PORTS)
        miss_req_addr = Array(Signal(name="miss_req_addr", 64) \
                                    for i in range(NR_PORTS))
        miss_req_wdata = Array(Signal(name="miss_req_wdata", 64) \
                                    for i in range(NR_PORTS))
        miss_req_we = Signal(self.NR_PORTS)
        miss_req_be = Array(Signal(name="miss_req_be", 8) \
                                    for i in range(NR_PORTS))
        miss_req_size = Array(Signal(name="miss_req_size", 2) \
                                    for i in range(NR_PORTS))

        # Cache Line Refill <-> AXI
        req_fsm_miss_valid = Signal()
        req_fsm_miss_addr = Signal(64)
        req_fsm_miss_wdata = Signal(DCACHE_LINE_WIDTH)
        req_fsm_miss_we = Signal()
        req_fsm_miss_be = Signal(DCACHE_LINE_WIDTH//8)
        ariane_axi::ad_req_t                     req_fsm_miss_req;
        req_fsm_miss_size = Signal(2)

        gnt_miss_fsm = Signal()
        valid_miss_fsm = Signal()
        nmiss = DCACHE_LINE_WIDTH//64
        data_miss_fsm = Array(Signal(name="data_miss_fsm", 64) \
                                    for i in range(nmiss))

        # Cache Management <-> LFSR
        lfsr_enable = Signal()
        lfsr_oh = Signal(DCACHE_SET_ASSOC)
        lfsr_bin = Signal($clog2(DCACHE_SET_ASSOC-1))
        # AMOs
        ariane_pkg::amo_t amo_op;
        amo_operand_a = Signal(64)
        amo_operand_b = Signal(64)
        amo_result_o = Signal(64)

        struct packed {
            logic [63:3] address;
            logic        valid;
        } reservation_d, reservation_q;

        # ------------------------------
        # Cache Management
        # ------------------------------
        evict_way = Signal(DCACHE_SET_ASSOC)
        valid_way = Signal(DCACHE_SET_ASSOC)

        for (i in range(DCACHE_SET_ASSOC):
            comb += evict_way[i].eq(data_i[i].valid & data_i[i].dirty)
            comb += valid_way[i].eq(data_i[i].valid)

        # ----------------------
        # Default Assignments
        # ----------------------
        # to AXI refill
        req_fsm_miss_req    = ariane_axi::CACHE_LINE_REQ;
        req_fsm_miss_size   = Const(0b11, 2)
        # core
        serve_amo_d         = serve_amo_q;
        # --------------------------------
        # Flush and Miss operation
        # --------------------------------
        state_d      = state_q;
        cnt_d        = cnt_q;
        evict_way_d  = evict_way_q;
        evict_cl_d   = evict_cl_q;
        mshr_d       = mshr_q;
        # communicate to the requester which unit we are currently serving
        active_serving_o[mshr_q.id] = mshr_q.valid;
        # AMOs
        # silence the unit when not used
        amo_op = amo_req_i.amo_op;

        reservation_d = reservation_q;
        with m.FSM() as state_q:

            with m.Case("IDLE"):
                # lowest priority are AMOs, wait until everything else
                # is served before going for the AMOs
                with m.If (amo_req_i.req & ~busy_i):
                    # 1. Flush the cache
                    with m.If(~serve_amo_q):
                        m.next = "FLUSH_REQ_STATUS"
                        serve_amo_d.eq(0b1
                        cnt_d.eq(0
                    # 2. Do the AMO
                    with m.Else():
                        m.next = "AMO_LOAD"
                        serve_amo_d.eq(0b0

                # check if we want to flush and can flush
                # e.g.: we are not busy anymore
                # TODO: Check that the busy flag is indeed needed
                with m.If (flush_i & ~busy_i):
                    m.next = "FLUSH_REQ_STATUS"
                    cnt_d = 0

                # check if one of the state machines missed
                for i in range(NR_PORTS):
                    # here comes the refill portion of code
                    with m.If (miss_req_valid[i] & ~miss_req_bypass[i]):
                        m.next = "MISS"
                        # we are taking another request so don't
                        # take the AMO
                        serve_amo_d  = 0b0;
                        # save to MSHR
                        wid = DCACHE_TAG_WIDTH+DCACHE_INDEX_WIDTH
                        comb += [ mshr_d.valid.eq(0b1),
                                  mshr_d.we.eq(miss_req_we[i]),
                                  mshr_d.id.eq(i),
                                  mshr_d.addr.eq(miss_req_addr[i][0:wid]),
                                  mshr_d.wdata.eq(miss_req_wdata[i]),
                                  mshr_d.be.eq(miss_req_be[i]),
                                ]
                        break

            #  ~> we missed on the cache
            with m.Case("MISS"):
                # 1. Check if there is an empty cache-line
                # 2. If not -> evict one
                comb += req_o.eq(1)
                sync += addr_o.eq(mshr_q.addr[:DCACHE_INDEX_WIDTH]
                m.next = "MISS_REPL"
                comb += miss_o.eq(1)

            # ~> second miss cycle
            with m.Case("MISS_REPL"):
                # if all are valid we need to evict one, 
                # pseudo random from LFSR
                with m.If(~(~valid_way).bool()):
                    comb += lfsr_enable.eq(0b1)
                    comb += evict_way_d.eq(lfsr_oh)
                    # do we need to write back the cache line?
                    with m.If(data_i[lfsr_bin].dirty):
                        state_d = WB_CACHELINE_MISS;
                        comb += evict_cl_d.tag.eq(data_i[lfsr_bin].tag)
                        comb += evict_cl_d.data.eq(data_i[lfsr_bin].data)
                        comb += cnt_d.eq(mshr_q.addr[:DCACHE_INDEX_WIDTH])
                    # no - we can request a cache line now
                    with m.Else():
                        m.next = "REQ_CACHELINE"
                # we have at least one free way
                with m.Else():
                    # get victim cache-line by looking for the
                    # first non-valid bit
                    comb += evict_way_d.eq(get_victim_cl(~valid_way)
                    m.next = "REQ_CACHELINE"

            # ~> we can just load the cache-line,
            # the way is store in evict_way_q
            with m.Case("REQ_CACHELINE"):
                comb += req_fsm_miss_valid .eq(1)
                sync += req_fsm_miss_addr  .eq(mshr_q.addr)

                with m.If (gnt_miss_fsm):
                    m.next = "SAVE_CACHELINE"
                    comb += miss_gnt_o[mshr_q.id].eq(1)

            # ~> replace the cacheline
            with m.Case("SAVE_CACHELINE"):
                # calculate cacheline offset
                automatic logic [$clog2(DCACHE_LINE_WIDTH)-1:0] cl_offset;
                sync += cl_offset.eq(mshr_q.addr[3:DCACHE_BYTE_OFFSET] << 6)
                # we've got a valid response from refill unit
                with m.If (valid_miss_fsm):
                    wid = DCACHE_TAG_WIDTH+DCACHE_INDEX_WIDTH
                    sync += addr_o      .eq(mshr_q.addr[:DCACHE_INDEX_WIDTH])
                    sync += req_o       .eq(evict_way_q)
                    comb += we_o        .eq(1)
                    comb += be_o        .eq(1)
                    sync += be_o.vldrty .eq(evict_way_q)
                    sync += data_o.tag  .eq(mshr_q.addr[DCACHE_INDEX_WIDTH:wid]
                    comb += data_o.data .eq(data_miss_fsm)
                    comb += data_o.valid.eq(1)
                    comb += data_o.dirty.eq(0)

                    # is this a write?
                    with m.If (mshr_q.we):
                        # Yes, so safe the updated data now
                        for i in range(8):
                            # check if we really want to write
                            # the corresponding byte
                            with m.If (mshr_q.be[i]):
                                sync += data_o.data[(cl_offset + i*8) +: 8].eq(mshr_q.wdata[i];
                        # it's immediately dirty if we write
                        comb += data_o.dirty.eq(1)

                    # reset MSHR
                    comb += mshr_d.valid.eq(0)
                    # go back to idle
                    m.next = 'IDLE'

            # ------------------------------
            # Write Back Operation
            # ------------------------------
            # ~> evict a cache line from way saved in evict_way_q
            with m.Case("WB_CACHELINE_FLUSH"):
            with m.Case("WB_CACHELINE_MISS"):

                comb += req_fsm_miss_valid .eq(0b1)
                sync += req_fsm_miss_addr  .eq({evict_cl_q.tag, cnt_q[DCACHE_INDEX_WIDTH-1:DCACHE_BYTE_OFFSET], {{DCACHE_BYTE_OFFSET}{0b0}}};
                comb += req_fsm_miss_be    .eq(1)
                comb += req_fsm_miss_we    .eq(0b1)
                sync += req_fsm_miss_wdata .eq(evict_cl_q.data;

                # we've got a grant --> this is timing critical, think about it
                if (gnt_miss_fsm) begin
                    # write status array
                    sync += addr_o    .eq(cnt_q)
                    comb += req_o     .eq(0b1)
                    comb += we_o      .eq(0b1)
                    comb += data_o.valid.eq(INVALIDATE_ON_FLUSH ? 0b0 : 0b1)
                    # invalidate
                    sync += be_o.vldrty.eq(evict_way_q)
                    # go back to handling the miss or flushing,
                    # depending on where we came from
                    with m.If(state_q == WB_CACHELINE_MISS):
                        m.next = "MISS"
                    with m.Else():
                        m.next = "FLUSH_REQ_STATUS"

            # ------------------------------
            # Flushing & Initialization
            # ------------------------------
            # ~> make another request to check the same
            # cache-line if there are still some valid entries
            with m.Case("FLUSH_REQ_STATUS"):
                comb += req_o  .eq(1)
                sync += addr_o .eq(cnt_q)
                m.next = "FLUSHING"

            with m.Case("FLUSHING"):
                # this has priority
                # at least one of the cache lines is dirty
                with m.If(~evict_way):
                    # evict cache line, look for the first
                    # cache-line which is dirty
                    comb += evict_way_d.eq(get_victim_cl(evict_way))
                    comb += evict_cl_d .eq(data_i[one_hot_to_bin(evict_way)])
                    state_d     = WB_CACHELINE_FLUSH;
                # not dirty ~> increment and continue
                with m.Else():
                    # increment and re-request
                    sync += cnt_d.eq(cnt_q + (1 << DCACHE_BYTE_OFFSET))
                    m.next = "FLUSH_REQ_STATUS"
                    sync += addr_o     .eq(cnt_q)
                    comb += req_o      .eq(1)
                    comb += be_o.vldrty.eq(INVALIDATE_ON_FLUSH ? 1 : 0)
                    comb += we_o       .eq(1)
                    # finished with flushing operation, go back to idle
                    with m.If (cnt_q[DCACHE_BYTE_OFFSET:DCACHE_INDEX_WIDTH] \
                               == DCACHE_NUM_WORDS-1):
                        # only acknowledge if the flush wasn't
                        # triggered by an atomic
                        sync += flush_ack_o.eq(~serve_amo_q)
                        m.next = "IDLE"

            # ~> only called after reset
            with m.Case("INIT"):
                # initialize status array
                sync += addr_o.eq(cnt_q)
                comb += req_o .eq(1)
                comb += we_o  .eq(1)
                # only write the dirty array
                comb += be_o.vldrty.eq(1)
                sync += cnt_d      .eq(cnt_q + (1 << DCACHE_BYTE_OFFSET))
                # finished initialization
                with m.If (cnt_q[DCACHE_BYTE_OFFSET:DCACHE_INDEX_WIDTH] \
                            == DCACHE_NUM_WORDS-1)
                    m.next = "IDLE"

            # ----------------------
            # AMOs
            # ----------------------
            # TODO(zarubaf) Move this closer to memory
            # ~> we are here because we need to do the AMO,
            # the cache is clean at this point
            # start by executing the load
            with m.Case("AMO_LOAD"):
                comb += req_fsm_miss_valid.eq(1)
                # address is in operand a
                comb += req_fsm_miss_addr.eq(amo_req_i.operand_a)
                comb += req_fsm_miss_req.eq(ariane_axi::SINGLE_REQ)
                comb += req_fsm_miss_size.eq(amo_req_i.size)
                # the request has been granted
                with m.If(gnt_miss_fsm):
                    m.next = "AMO_SAVE_LOAD"
            # save the load value
            with m.Case("AMO_SAVE_LOAD"):
                with m.If (valid_miss_fsm):
                    # we are only concerned about the lower 64-bit
                    comb += mshr_d.wdata.eq(data_miss_fsm[0])
                    m.next = "AMO_STORE"
            # and do the store
            with m.Case("AMO_STORE"):
                load_data = Signal(64)
                # re-align load data
                comb += load_data.eq(data_align(amo_req_i.operand_a[:3],
                                                mshr_q.wdata))
                # Sign-extend for word operation
                with m.If (amo_req_i.size == 0b10):
                    comb += amo_operand_a.eq(sext32(load_data[:32]))
                    comb += amo_operand_b.eq(sext32(amo_req_i.operand_b[:32]))
                with m.Else():
                    comb += amo_operand_a.eq(load_data)
                    comb += amo_operand_b.eq(amo_req_i.operand_b)

                #  we do not need a store request for load reserved
                # or a failing store conditional
                #  we can bail-out without making any further requests
                with m.If ((amo_req_i.amo_op == AMO_LR) | \
                           ((amo_req_i.amo_op == AMO_SC) & \
                           ((reservation_q.valid & \
                            (reservation_q.address != \
                             amo_req_i.operand_a[3:64])) | \
                             ~reservation_q.valid))):
                    comb += req_fsm_miss_valid.eq(0)
                    m.next = "IDLE"
                    comb += amo_resp_o.ack.eq(1)
                    # write-back the result
                    comb += amo_resp_o.result.eq(amo_operand_a)
                    # we know that the SC failed
                    with m.If (amo_req_i.amo_op == AMO_SC):
                        comb += amo_resp_o.result.eq(1)
                        # also clear the reservation
                        comb += reservation_d.valid.eq(0)
                with m.Else():
                    comb += req_fsm_miss_valid.eq(1)

                comb += req_fsm_miss_we  .eq(1)
                comb += req_fsm_miss_req .eq(ariane_axi::SINGLE_REQ)
                comb += req_fsm_miss_size.eq(amo_req_i.size)
                comb += req_fsm_miss_addr.eq(amo_req_i.operand_a)

                comb += req_fsm_miss_wdata.eq(
                    data_align(amo_req_i.operand_a[0:3], amo_result_o))
                comb += req_fsm_miss_be.eq(
                    be_gen(amo_req_i.operand_a[0:3], amo_req_i.size))

                # place a reservation on the memory
                with m.If (amo_req_i.amo_op == AMO_LR):
                    comb += reservation_d.address.eq(amo_req_i.operand_a[3:64])
                    comb += reservation_d.valid.eq(1)

                # the request is valid or we didn't need to go for another store
                with m.If (valid_miss_fsm):
                    m.next = "IDLE"
                    comb += amo_resp_o.ack.eq(1)
                    # write-back the result
                    comb += amo_resp_o.result.eq(amo_operand_a;

                    if (amo_req_i.amo_op == AMO_SC) begin
                        comb += amo_resp_o.result.eq(0)
                        # An SC must fail if there is another SC
                        # (to any address) between the LR and the SC in
                        # program order (even to the same address).
                        # in any case destroy the reservation
                        comb += reservation_d.valid.eq(0)

        # check MSHR for aliasing

        comb += mshr_addr_matches_o .eq(0)
        comb += mshr_index_matches_o.eq()

        for i in range(NR_PORTS):
            # check mshr for potential matching of other units,
            # exclude the unit currently being served
            with m.If (mshr_q.valid & \
                    (mshr_addr_i[i][DCACHE_BYTE_OFFSET:56] == \
                     mshr_q.addr[DCACHE_BYTE_OFFSET:56])):
                comb += mshr_addr_matches_o[i].eq(1)

            # same as previous, but checking only the index
            with m.If (mshr_q.valid & \
                    (mshr_addr_i[i][DCACHE_BYTE_OFFSET:DCACHE_INDEX_WIDTH] == \
                     mshr_q.addr[DCACHE_BYTE_OFFSET:DCACHE_INDEX_WIDTH])):
                mshr_index_matches_o[i].eq(1)

        # --------------------
        # Sequential Process
        # --------------------

        """
        #pragma translate_off
        `ifndef VERILATOR
        # assert that cache only hits on one way
        assert property (
          @(posedge clk_i) $onehot0(evict_way_q)) else $warning("Evict-way should be one-hot encoded");
        `endif
        #pragma translate_on
        """

        # ----------------------
        # Bypass Arbiter
        # ----------------------
        # Connection Arbiter <-> AXI
        req_fsm_bypass_valid = Signal()
        req_fsm_bypass_addr = Signal(64)
        req_fsm_bypass_wdata = Signal(64)
        req_fsm_bypass_we = Signal()
        req_fsm_bypass_be = Signal(8)
        req_fsm_bypass_size = Signal(2)
        gnt_bypass_fsm = Signal()
        valid_bypass_fsm = Signal()
        data_bypass_fsm = Signal(64)
        logic [$clog2(NR_PORTS)-1:0] id_fsm_bypass;
        logic [3:0]                  id_bypass_fsm;
        logic [3:0]                  gnt_id_bypass_fsm;

        i_bypass_arbiter = ib = AXIArbiter( NR_PORTS, 64)
        comb += [
            # Master Side
            ib.data_req_i     .eq( miss_req_valid & miss_req_bypass         ),
            ib.address_i      .eq( miss_req_addr                            ),
            ib.data_wdata_i   .eq( miss_req_wdata                           ),
            ib.data_we_i      .eq( miss_req_we                              ),
            ib.data_be_i      .eq( miss_req_be                              ),
            ib.data_size_i    .eq( miss_req_size                            ),
            ib.data_gnt_o     .eq( bypass_gnt_o                             ),
            ib.data_rvalid_o  .eq( bypass_valid_o                           ),
            ib.data_rdata_o   .eq( bypass_data_o                            ),
            # Slave Sid
            ib.id_i           .eq( id_bypass_fsm[$clog2(NR_PORTS)-1:0]      ),
            ib.id_o           .eq( id_fsm_bypass                            ),
            ib.gnt_id_i       .eq( gnt_id_bypass_fsm[$clog2(NR_PORTS)-1:0]  ),
            ib.address_o      .eq( req_fsm_bypass_addr                      ),
            ib.data_wdata_o   .eq( req_fsm_bypass_wdata                     ),
            ib.data_req_o     .eq( req_fsm_bypass_valid                     ),
            ib.data_we_o      .eq( req_fsm_bypass_we                        ),
            ib.data_be_o      .eq( req_fsm_bypass_be                        ),
            ib.data_size_o    .eq( req_fsm_bypass_size                      ),
            ib.data_gnt_i     .eq( gnt_bypass_fsm                           ),
            ib.data_rvalid_i  .eq( valid_bypass_fsm                         ),
            ib.data_rdata_i   .eq( data_bypass_fsm                          ),
        ]

        axi_adapter #(
            .DATA_WIDTH            ( 64                 ),
            .AXI_ID_WIDTH          ( 4                  ),
            .CACHELINE_BYTE_OFFSET ( DCACHE_BYTE_OFFSET )
        ) i_bypass_axi_adapter (
            .clk_i,
            .rst_ni,
            .req_i                 ( req_fsm_bypass_valid   ),
            .type_i                ( ariane_axi::SINGLE_REQ ),
            .gnt_o                 ( gnt_bypass_fsm         ),
            .addr_i                ( req_fsm_bypass_addr    ),
            .we_i                  ( req_fsm_bypass_we      ),
            .wdata_i               ( req_fsm_bypass_wdata   ),
            .be_i                  ( req_fsm_bypass_be      ),
            .size_i                ( req_fsm_bypass_size    ),
            .id_i                  ( Cat(id_fsm_bypass, 0, 0) ),
            .valid_o               ( valid_bypass_fsm       ),
            .rdata_o               ( data_bypass_fsm        ),
            .gnt_id_o              ( gnt_id_bypass_fsm      ),
            .id_o                  ( id_bypass_fsm          ),
            .critical_word_o       (                        ), # not used for single requests
            .critical_word_valid_o (                        ), # not used for single requests
            .axi_req_o             ( axi_bypass_o           ),
            .axi_resp_i            ( axi_bypass_i           )
        );

        # ----------------------
        # Cache Line AXI Refill
        # ----------------------
        axi_adapter  #(
            .DATA_WIDTH            ( DCACHE_LINE_WIDTH  ),
            .AXI_ID_WIDTH          ( 4                  ),
            .CACHELINE_BYTE_OFFSET ( DCACHE_BYTE_OFFSET )
        ) i_miss_axi_adapter (
            .clk_i,
            .rst_ni,
            .req_i               ( req_fsm_miss_valid ),
            .type_i              ( req_fsm_miss_req   ),
            .gnt_o               ( gnt_miss_fsm       ),
            .addr_i              ( req_fsm_miss_addr  ),
            .we_i                ( req_fsm_miss_we    ),
            .wdata_i             ( req_fsm_miss_wdata ),
            .be_i                ( req_fsm_miss_be    ),
            .size_i              ( req_fsm_miss_size  ),
            .id_i                ( Const(0b1100, 4)   ),
            .gnt_id_o            (                    ), # open
            .valid_o             ( valid_miss_fsm     ),
            .rdata_o             ( data_miss_fsm      ),
            .id_o                (                    ),
            .critical_word_o,
            .critical_word_valid_o,
            .axi_req_o           ( axi_data_o         ),
            .axi_resp_i          ( axi_data_i         )
        );

        # -----------------
        # Replacement LFSR
        # -----------------
        lfsr_8bit #(.WIDTH (DCACHE_SET_ASSOC)) i_lfsr (
            .en_i           ( lfsr_enable ),
            .refill_way_oh  ( lfsr_oh     ),
            .refill_way_bin ( lfsr_bin    ),
            .*
        );

        # -----------------
        # AMO ALU
        # -----------------
        amo_alu i_amo_alu (
            .amo_op_i        ( amo_op        ),
            .amo_operand_a_i ( amo_operand_a ),
            .amo_operand_b_i ( amo_operand_b ),
            .amo_result_o    ( amo_result_o  )
        );

        # -----------------
        # Struct Split
        # -----------------

        for i in range(NR_PORTS):
            miss_req = MissReq()
            comb += miss_req.eq(miss_req_i[i]);
            comb += miss_req_valid  [i] .eq(miss_req.valid)
            comb += miss_req_bypass [i] .eq(miss_req.bypass)
            comb += miss_req_addr   [i] .eq(miss_req.addr)
            comb += miss_req_wdata  [i] .eq(miss_req.wdata)
            comb += miss_req_we     [i] .eq(miss_req.we)
            comb += miss_req_be     [i] .eq(miss_req.be)
            comb += miss_req_size   [i] .eq(miss_req.size)

    # --------------
    # AXI Arbiter
    # --------------s
    #
    # Description: Arbitrates access to AXI refill/bypass
    #
class AXIArbiter:
    def __init__(self, NR_PORTS   = 3, DATA_WIDTH = 64):
        self.NR_PORTS = NR_PORTS
        self.DATA_WIDTH = DATA_WIDTH
        self.pwid = pwid = ceil(log(NR_PORTS) / log(2))
        rst_ni = ResetSignal() # Asynchronous reset active low
        # master ports
        self.data_req_i = Signal(NR_PORTS)
        self.address_i = Array(Signal(name="address_i", 64) \
                                    for i in range(NR_PORTS))
        self.data_wdata_i = Array(Signal(name="data_wdata_i", 64) \
                                    for i in range(NR_PORTS))
        self.data_we_i = Signal(NR_PORTS)
        self.data_be_i = Array(Signal(name="data_wdata_i", DATA_WIDTH/8) \
                                    for i in range(NR_PORTS))
        self.data_size_i = Array(Signal(name="data_size_i", 2) \
                                    for i in range(NR_PORTS))
        self.data_gnt_o = Signal(NR_PORTS)
        self.data_rvalid_o = Signal(NR_PORTS)
        self.data_rdata_o = Array(Signal(name="data_rdata_o", 64) \
                                    for i in range(NR_PORTS))

        # slave port
        self.id_i = Signal(pwid)
        self.id_o = Signal(pwid)
        self.gnt_id_i = Signal(pwid)
        self.data_req_o = Signal()
        self.address_o = Signal(64)
        self.data_wdata_o = Signal(DATA_WIDTH)
        self.data_we_o = Signal()
        self.data_be_o = Signal(DATA_WIDTH/8)
        self.data_size_o = Signal(2)
        self.data_gnt_i = Signal()
        self.data_rvalid_i = Signal()
        self.data_rdata_i = Signal(DATA_WIDTH)

    def elaborate(self, platform):
        #enum logic [1:0] { IDLE, REQ, SERVING } state_d, state_q;

        class Packet:
            def __init__(self, pwid, DATA_WIDTH):
                self.id = Signal(pwid)
                self.address = Signal(64)
                self.data = Signal(64)
                self.size = Signal(2)
                self.be = Signal(DATA_WIDTH/8)
                self.we = Signal()

        request_index = Signal(self.pwid)
        req_q = Packet(self.pwid, self.DATA_WIDTH)
        req_d = Packet(self.pwid, self.DATA_WIDTH)

        # request register
        sync += req_q.eq(req_d)

        # request port
        comb += self.address_o             .eq(req_q.address)
        comb += self.data_wdata_o          .eq(req_q.data)
        comb += self.data_be_o             .eq(req_q.be)
        comb += self.data_size_o           .eq(req_q.size)
        comb += self.data_we_o             .eq(req_q.we)
        comb += self.id_o                  .eq(req_q.id)
        comb += self.data_gnt_o            .eq(0)
        # read port
        comb += self.data_rvalid_o         .eq(0)
        comb += self.data_rdata_o          .eq(0)
        comb += self.data_rdata_o[req_q.id].eq(data_rdata_i)

        m.submodules.pp = pp = PriorityEncoder(self.NR_PORTS)
        comb += pp.i.eq(self.data_req_i) # select one request (priority-based)
        comb += request_index.eq(pp.o)

        with m.Switch("state") as s:

            with m.Case("IDLE"):
                # wait for incoming requests (priority encoder data_req_i)
                with m.If(~pp.n): # one output valid from encoder
                    comb += self.data_req_o   .eq(self.data_req_i[i])
                    comb += self.data_gnt_o[i].eq(self.data_req_i[i])
                    # save the request
                    comb += req_d.address.eq(self.address_i[i])
                    comb += req_d.id.eq(request_index)
                    comb += req_d.data.eq(self.data_wdata_i[i])
                    comb += req_d.size.eq(self.data_size_i[i])
                    comb += req_d.be.eq(self.data_be_i[i])
                    comb += req_d.we.eq(self.data_we_i[i])
                    m.next = "SERVING"

                comb += self.address_o    .eq(self.address_i[request_index])
                comb += self.data_wdata_o .eq(self.data_wdata_i[request_index])
                comb += self.data_be_o    .eq(self.data_be_i[request_index])
                comb += self.data_size_o  .eq(self.data_size_i[request_index])
                comb += self.data_we_o    .eq(self.data_we_i[request_index])
                comb += self.id_o         .eq(request_index)

            with m.Case("SERVING"):
                comb += self.data_req_o.eq(1)
                with m.If (self.data_rvalid_i):
                    comb += self.data_rvalid_o[req_q.id].eq(1)
                    m.next = "IDLE"

        # ------------
        # Assertions
        # ------------

        """
#pragma translate_off
`ifndef VERILATOR
# make sure that we eventually get an rvalid after we received a grant
assert property (@(posedge clk_i) data_gnt_i |-> ##[1:$] data_rvalid_i )
    else begin $error("There was a grant without a rvalid"); $stop(); end
# assert that there is no grant without a request
assert property (@(negedge clk_i) data_gnt_i |-> data_req_o)
    else begin $error("There was a grant without a request."); $stop(); end
# assert that the address does not contain X when request is sent
assert property ( @(posedge clk_i) (data_req_o) |-> (!$isunknown(address_o)) )
  else begin $error("address contains X when request is set"); $stop(); end

`endif
#pragma translate_on
        """

