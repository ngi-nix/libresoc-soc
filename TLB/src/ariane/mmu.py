"""
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
# Date: 19/04/2017
# Description: Memory Management Unit for Ariane, contains TLB and
#              address translation unit. SV39 as defined in RISC-V
#              privilege specification 1.11-WIP

import ariane_pkg::*;
"""

from nmigen import Const, Signal, Cat, Module
from ptw import DCacheReqI, DCacheReqO, TLBUpdate, PTE, PTW
from tlb import TLB


PRIV_LVL_M = Const(0b11, 2)
PRIV_LVL_S = Const(0b01, 2)
PRIV_LVL_U = Const(0b00, 2)


class RVException:
    def __init__(self):
         self.cause = Signal(64) # cause of exception
         self.tval = Signal(64) # more info of causing exception
                                # (e.g.: instruction causing it),
                                #        address of LD/ST fault
         self.valid = Signal()

    def __iter__(self):
        yield self.cause
        yield self.tval
        yield self.valid

    def ports(self):
        return list(self)


class ICacheReqI:
    def __init__(self):
        self.fetch_valid = Signal()   # address translation valid
        self.fetch_paddr = Signal(64) # physical address in
        self.fetch_exception = RVException() // exception occurred during fetch

    def __iter__(self):
        yield self.fetch_valid
        yield self.fetch_paddr
        yield from self.fetch_exception

    def ports(self):
        return list(self)


class ICacheReqO:
    def __init__(self):
        self.fetch_req = Signal()     # address translation request
        self.fetch_vaddr = Signal(64) # virtual address out

    def __iter__(self):
        yield self.fetch_req
        yield self.fetch_vaddr

    def ports(self):
        return list(self)


class MMU:
    def __init__(self, INSTR_TLB_ENTRIES = 4,
                       DATA_TLB_ENTRIES  = 4,
                       ASID_WIDTH        = 1):
        self.flush_i = Signal()
        self.enable_translation_i = Signal()
        self.en_ld_st_translation_i = Signal() # enable VM translation for LD/ST
        # IF interface
        self.icache_areq_i = ICacheReqO()
        self.icache_areq_o = ICacheReqI()
        # LSU interface
        # this is a more minimalistic interface because the actual addressing
        # logic is handled in the LSU as we distinguish load and stores,
        # what we do here is simple address translation
        self.misaligned_ex_i = RVException()
        self.lsu_req_i = Signal()   # request address translation
        self.lsu_vaddr_i = Signal(64) # virtual address in
        self.lsu_is_store_i = Signal() # the translation is requested by a store
        # if we need to walk the page table we can't grant in the same cycle

        # Cycle 0
        self.lsu_dtlb_hit_o = Signal() # sent in the same cycle as the request
                                       # if translation hits in the DTLB
        # Cycle 1
        self.lsu_valid_o = Signal()  # translation is valid
        self.lsu_paddr_o = Signal(64) # translated address
        self.lsu_exception_o = RVException() # addr translate threw exception

        # General control signals
        self.priv_lvl_i = Signal(2)
        self.ld_st_priv_lvl_i = Signal(2)
        self.sum_i = Signal()
        self.mxr_i = Signal()
        # input logic flag_mprv_i,
        self.satp_ppn_i = Signal(44)
        self.asid_i = Signal(ASID_WIDTH)
        self.flush_tlb_i = Signal()
        # Performance counters
        self.itlb_miss_o = Signal()
        self.dtlb_miss_o = Signal()
        # PTW memory interface
        self.req_port_i = DCacheReqO()
        self.req_port_o = DCacheReqI()

    def elaborate(self, platform):
        iaccess_err = Signal()   # insufficient priv to access instr page
        daccess_err = Signal()   # insufficient priv to access data page
        ptw_active = Signal()    # PTW is currently walking a page table
        walking_instr = Signal() # PTW is walking because of an ITLB miss
        ptw_error = Signal()     # PTW threw an exception

        update_vaddr = Signal(39)
        update_ptw_itlb = TLBUpdate()
        update_ptw_dtlb = TLBUpdate()

        itlb_lu_access = Signal()
        itlb_content = PTE()
        itlb_is_2M = Signal()
        itlb_is_1G = Signal()
        itlb_lu_hit = Signal()

        dtlb_lu_access = Signal()
        dtlb_content = PTE()
        dtlb_is_2M = Signal()
        dtlb_is_1G = Signal()
        dtlb_lu_hit = Signal()

        # Assignments
        m.d.comb += [itlb_lu_access.eq(icache_areq_i.fetch_req),
                     dtlb_lu_access.eq(lsu_req_i)
                    ]


        # ITLB
        m.submodules.i_tlb = i_tlb = TLB(INSTR_TLB_ENTRIES, ASID_WIDTH)
        m.d.comb += [i_tlb.flush_i.eq(flush_tlb_i),
                     i_tlb.update_i.eq(update_ptw_itlb),
                     i_tlb.lu_access_i.eq(itlb_lu_access),
                     i_tlb.lu_asid_i.eq(asid_i),
                     i_tlb.lu_vaddr_i.eq(icache_areq_i.fetch_vaddr),
                     itlb_content.eq(i_tlb.lu_content_o),
                     itlb_is_2M.eq(i_tlb.lu_is_2M_o),
                     itlb_is_1G.eq(i_tlb.lu_is_1G_o),
                     itlb_lu_hit.eq(i_tlb.lu_hit_o),
                    ]

        # DTLB
        m.submodules.d_tlb = d_tlb = TLB(DATA_TLB_ENTRIES, ASID_WIDTH)
        m.d.comb += [d_tlb.flush_i.eq(flush_tlb_i),
                     d_tlb.update_i.eq(update_ptw_dtlb),
                     d_tlb.lu_access_i.eq(dtlb_lu_access),
                     d_tlb.lu_asid_i.eq(asid_i),
                     d_tlb.lu_vaddr_i.eq(lsu_vaddr_i),
                     dtlb_content.eq(d_tlb.lu_content_o),
                     dtlb_is_2M.eq(d_tlb.lu_is_2M_o),
                     dtlb_is_1G.eq(d_tlb.lu_is_1G_o),
                     dtlb_lu_hit.eq(d_tlb.lu_hit_o),
                    ]

        # PTW
        m.submodules.ptw = ptw = PTW(ASID_WIDTH)
        m.d.comb += [ptw_active.eq(ptw.ptw_active_o),
                     walking_instr.eq(ptw.walking_instr_o),
                     ptw_error.eq(ptw.ptw_error_o),
                     ptw.enable_translation_i.eq(enable_translation_i),

                     update_vaddr.eq(ptw.update_vaddr_o),
                     update_ptw_itlb.eq(ptw.itlb_update_o),
                     update_ptw_dtlb.eq(ptw.dtlb_update_o),

                     ptw.itlb_access_i.eq(itlb_lu_access),
                     ptw.itlb_hit_i.eq(itlb_lu_hit),
                     ptw.itlb_vaddr_i.eq(icache_areq_i.fetch_vaddr),

                     ptw.dtlb_access_i.eq(dtlb_lu_access),
                     ptw.dtlb_hit_i.eq(dtlb_lu_hit),
                     ptw.dtlb_vaddr_i.eq(lsu_vaddr_i),

                     ptw.req_port_i.eq(req_port_i),
                     req_port_o.eq(ptw.req_port_o),
                    ]

        # ila_1 i_ila_1 (
        #     .clk(clk_i), # input wire clk
        #     .probe0({req_port_o.address_tag, req_port_o.address_index}),
        #     .probe1(req_port_o.data_req), # input wire [63:0]  probe1
        #     .probe2(req_port_i.data_gnt), # input wire [0:0]  probe2
        #     .probe3(req_port_i.data_rdata), # input wire [0:0]  probe3
        #     .probe4(req_port_i.data_rvalid), # input wire [0:0]  probe4
        #     .probe5(ptw_error), # input wire [1:0]  probe5
        #     .probe6(update_vaddr), # input wire [0:0]  probe6
        #     .probe7(update_ptw_itlb.valid), # input wire [0:0]  probe7
        #     .probe8(update_ptw_dtlb.valid), # input wire [0:0]  probe8
        #     .probe9(dtlb_lu_access), # input wire [0:0]  probe9
        #     .probe10(lsu_vaddr_i), # input wire [0:0]  probe10
        #     .probe11(dtlb_lu_hit), # input wire [0:0]  probe11
        #     .probe12(itlb_lu_access), # input wire [0:0]  probe12
        #     .probe13(icache_areq_i.fetch_vaddr), # input wire [0:0]  probe13
        #     .probe14(itlb_lu_hit) # input wire [0:0]  probe13
        # );

        #-----------------------
        # Instruction Interface
        #-----------------------
        # The instruction interface is a simple request response interface
        always_comb begin : instr_interface
            # MMU disabled: just pass through
            icache_areq_o.fetch_valid  = icache_areq_i.fetch_req;
            icache_areq_o.fetch_paddr  = icache_areq_i.fetch_vaddr; # play through in case we disabled address translation
            # two potential exception sources:
            # 1. HPTW threw an exception -> signal with a page fault exception
            # 2. We got an access error because of insufficient permissions -> throw an access exception
            icache_areq_o.fetch_exception      = '0;
            # Check whether we are allowed to access this memory region from a fetch perspective
            iaccess_err   = icache_areq_i.fetch_req && (((priv_lvl_i == riscv::PRIV_LVL_U) && ~itlb_content.u)
                                                     || ((priv_lvl_i == riscv::PRIV_LVL_S) && itlb_content.u));

            # MMU enabled: address from TLB, request delayed until hit. Error when TLB
            # hit and no access right or TLB hit and translated address not valid (e.g.
            # AXI decode error), or when PTW performs walk due to ITLB miss and raises
            # an error.
            if (enable_translation_i) begin
                # we work with SV39, so if VM is enabled, check that all bits [63:38] are equal
                if (icache_areq_i.fetch_req && !((&icache_areq_i.fetch_vaddr[63:38]) == 1'b1 || (|icache_areq_i.fetch_vaddr[63:38]) == 1'b0)) begin
                    icache_areq_o.fetch_exception = {riscv::INSTR_ACCESS_FAULT, icache_areq_i.fetch_vaddr, 1'b1};
                end

                icache_areq_o.fetch_valid = 1'b0;

                # 4K page
                icache_areq_o.fetch_paddr = {itlb_content.ppn, icache_areq_i.fetch_vaddr[11:0]};
                # Mega page
                if (itlb_is_2M) begin
                    icache_areq_o.fetch_paddr[20:12] = icache_areq_i.fetch_vaddr[20:12];
                end
                # Giga page
                if (itlb_is_1G) begin
                    icache_areq_o.fetch_paddr[29:12] = icache_areq_i.fetch_vaddr[29:12];
                end

                # ---------
                # ITLB Hit
                # --------
                # if we hit the ITLB output the request signal immediately
                if (itlb_lu_hit) begin
                    icache_areq_o.fetch_valid = icache_areq_i.fetch_req;
                    # we got an access error
                    if (iaccess_err) begin
                        # throw a page fault
                        icache_areq_o.fetch_exception = {riscv::INSTR_PAGE_FAULT, icache_areq_i.fetch_vaddr, 1'b1};
                    end
                end else
                # ---------
                # ITLB Miss
                # ---------
                # watch out for exceptions happening during walking the page table
                if (ptw_active && walking_instr) begin
                    icache_areq_o.fetch_valid = ptw_error;
                    icache_areq_o.fetch_exception = {riscv::INSTR_PAGE_FAULT, {25'b0, update_vaddr}, 1'b1};
                end
            end
        end

        #-----------------------
        # Data Interface
        #-----------------------
        logic [63:0] lsu_vaddr_n,     lsu_vaddr_q;
        riscv::pte_t dtlb_pte_n,      dtlb_pte_q;
        exception_t  misaligned_ex_n, misaligned_ex_q;
        logic        lsu_req_n,       lsu_req_q;
        logic        lsu_is_store_n,  lsu_is_store_q;
        logic        dtlb_hit_n,      dtlb_hit_q;
        logic        dtlb_is_2M_n,    dtlb_is_2M_q;
        logic        dtlb_is_1G_n,    dtlb_is_1G_q;

        # check if we need to do translation or if we are always ready (e.g.: we are not translating anything)
        assign lsu_dtlb_hit_o = (en_ld_st_translation_i) ? dtlb_lu_hit :  1'b1;

        # The data interface is simpler and only consists of a request/response interface
        always_comb begin : data_interface
            # save request and DTLB response
            lsu_vaddr_n           = lsu_vaddr_i;
            lsu_req_n             = lsu_req_i;
            misaligned_ex_n       = misaligned_ex_i;
            dtlb_pte_n            = dtlb_content;
            dtlb_hit_n            = dtlb_lu_hit;
            lsu_is_store_n        = lsu_is_store_i;
            dtlb_is_2M_n          = dtlb_is_2M;
            dtlb_is_1G_n          = dtlb_is_1G;

            lsu_paddr_o           = lsu_vaddr_q;
            lsu_valid_o           = lsu_req_q;
            lsu_exception_o       = misaligned_ex_q;
            # mute misaligned exceptions if there is no request otherwise they will throw accidental exceptions
            misaligned_ex_n.valid = misaligned_ex_i.valid & lsu_req_i;

            # Check if the User flag is set, then we may only access it in supervisor mode
            # if SUM is enabled
            daccess_err = (ld_st_priv_lvl_i == riscv::PRIV_LVL_S && !sum_i && dtlb_pte_q.u) || # SUM is not set and we are trying to access a user page in supervisor mode
                          (ld_st_priv_lvl_i == riscv::PRIV_LVL_U && !dtlb_pte_q.u);            # this is not a user page but we are in user mode and trying to access it
            # translation is enabled and no misaligned exception occurred
            if (en_ld_st_translation_i && !misaligned_ex_q.valid) begin
                lsu_valid_o = 1'b0;
                # 4K page
                lsu_paddr_o = {dtlb_pte_q.ppn, lsu_vaddr_q[11:0]};
                # Mega page
                if (dtlb_is_2M_q) begin
                  lsu_paddr_o[20:12] = lsu_vaddr_q[20:12];
                end
                # Giga page
                if (dtlb_is_1G_q) begin
                    lsu_paddr_o[29:12] = lsu_vaddr_q[29:12];
                end
                # ---------
                # DTLB Hit
                # --------
                if (dtlb_hit_q && lsu_req_q) begin
                    lsu_valid_o = 1'b1;
                    # this is a store
                    if (lsu_is_store_q) begin
                        # check if the page is write-able and we are not violating privileges
                        # also check if the dirty flag is set
                        if (!dtlb_pte_q.w || daccess_err || !dtlb_pte_q.d) begin
                            lsu_exception_o = {riscv::STORE_PAGE_FAULT, lsu_vaddr_q, 1'b1};
                        end

                    # this is a load, check for sufficient access privileges - throw a page fault if necessary
                    end else if (daccess_err) begin
                        lsu_exception_o = {riscv::LOAD_PAGE_FAULT, lsu_vaddr_q, 1'b1};
                    end
                end else

                # ---------
                # DTLB Miss
                # ---------
                # watch out for exceptions
                if (ptw_active && !walking_instr) begin
                    # page table walker threw an exception
                    if (ptw_error) begin
                        # an error makes the translation valid
                        lsu_valid_o = 1'b1;
                        # the page table walker can only throw page faults
                        if (lsu_is_store_q) begin
                            lsu_exception_o = {riscv::STORE_PAGE_FAULT, {25'b0, update_vaddr}, 1'b1};
                        end else begin
                            lsu_exception_o = {riscv::LOAD_PAGE_FAULT, {25'b0, update_vaddr}, 1'b1};
                        end
                    end
                end
            end
        end
        # ----------
        # Registers
        # ----------
        always_ff @(posedge clk_i or negedge rst_ni) begin
            if (~rst_ni) begin
                lsu_vaddr_q      <= '0;
                lsu_req_q        <= '0;
                misaligned_ex_q  <= '0;
                dtlb_pte_q       <= '0;
                dtlb_hit_q       <= '0;
                lsu_is_store_q   <= '0;
                dtlb_is_2M_q     <= '0;
                dtlb_is_1G_q     <= '0;
            end else begin
                lsu_vaddr_q      <=  lsu_vaddr_n;
                lsu_req_q        <=  lsu_req_n;
                misaligned_ex_q  <=  misaligned_ex_n;
                dtlb_pte_q       <=  dtlb_pte_n;
                dtlb_hit_q       <=  dtlb_hit_n;
                lsu_is_store_q   <=  lsu_is_store_n;
                dtlb_is_2M_q     <=  dtlb_is_2M_n;
                dtlb_is_1G_q     <=  dtlb_is_1G_n;
            end
        end
    endmodule
