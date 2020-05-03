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
#              address translation unit. SV48 as defined in
#              Volume II: RISC-V Privileged Architectures V1.10 Page 63

import ariane_pkg::*;
"""

from nmigen import Const, Signal, Cat, Module, Mux
from nmigen.cli import verilog, rtlil

from ptw import DCacheReqI, DCacheReqO, TLBUpdate, PTE, PTW
from tlb import TLB
from exceptcause import (INSTR_ACCESS_FAULT, INSTR_PAGE_FAULT,
                         LOAD_PAGE_FAULT, STORE_PAGE_FAULT)

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

    def eq(self, inp):
        res = []
        for (o, i) in zip(self.ports(), inp.ports()):
            res.append(o.eq(i))
        return res

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
        self.fetch_exception = RVException() # exception occurred during fetch

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
    def __init__(self, instr_tlb_entries = 4,
                       data_tlb_entries  = 4,
                       asid_width        = 1):
        self.instr_tlb_entries = instr_tlb_entries
        self.data_tlb_entries = data_tlb_entries
        self.asid_width = asid_width

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
        self.asid_i = Signal(self.asid_width)
        self.flush_tlb_i = Signal()
        # Performance counters
        self.itlb_miss_o = Signal()
        self.dtlb_miss_o = Signal()
        # PTW memory interface
        self.req_port_i = DCacheReqO()
        self.req_port_o = DCacheReqI()

    def elaborate(self, platform):
        m = Module()

        iaccess_err = Signal()   # insufficient priv to access instr page
        daccess_err = Signal()   # insufficient priv to access data page
        ptw_active = Signal()    # PTW is currently walking a page table
        walking_instr = Signal() # PTW is walking because of an ITLB miss
        ptw_error = Signal()     # PTW threw an exception

        update_vaddr = Signal(48)				  # guessed
        uaddr64 = Cat(update_vaddr, Const(0, 25)) # extend to 64bit with zeros
        update_ptw_itlb = TLBUpdate(self.asid_width)
        update_ptw_dtlb = TLBUpdate(self.asid_width)

        itlb_lu_access = Signal()
        itlb_content = PTE()
        itlb_is_2M = Signal()
        itlb_is_1G = Signal()
        itlb_is_512G = Signal()
        itlb_lu_hit = Signal()

        dtlb_lu_access = Signal()
        dtlb_content = PTE()
        dtlb_is_2M = Signal()
        dtlb_is_1G = Signal()
        dtlb_is_512G = Signal()
        dtlb_lu_hit = Signal()

        # Assignments
        m.d.comb += [itlb_lu_access.eq(self.icache_areq_i.fetch_req),
                     dtlb_lu_access.eq(self.lsu_req_i)
                    ]

        # ITLB
        m.submodules.i_tlb = i_tlb = TLB(self.instr_tlb_entries,
                                         self.asid_width)
        m.d.comb += [i_tlb.flush_i.eq(self.flush_tlb_i),
                     i_tlb.update_i.eq(update_ptw_itlb),
                     i_tlb.lu_access_i.eq(itlb_lu_access),
                     i_tlb.lu_asid_i.eq(self.asid_i),
                     i_tlb.lu_vaddr_i.eq(self.icache_areq_i.fetch_vaddr),
                     itlb_content.eq(i_tlb.lu_content_o),
                     itlb_is_2M.eq(i_tlb.lu_is_2M_o),
                     itlb_is_1G.eq(i_tlb.lu_is_1G_o),
                     itlb_is_512G.eq(i_tlb.lu_is_512G_o),
                     itlb_lu_hit.eq(i_tlb.lu_hit_o),
                    ]

        # DTLB
        m.submodules.d_tlb = d_tlb = TLB(self.data_tlb_entries,
                                         self.asid_width)
        m.d.comb += [d_tlb.flush_i.eq(self.flush_tlb_i),
                     d_tlb.update_i.eq(update_ptw_dtlb),
                     d_tlb.lu_access_i.eq(dtlb_lu_access),
                     d_tlb.lu_asid_i.eq(self.asid_i),
                     d_tlb.lu_vaddr_i.eq(self.lsu_vaddr_i),
                     dtlb_content.eq(d_tlb.lu_content_o),
                     dtlb_is_2M.eq(d_tlb.lu_is_2M_o),
                     dtlb_is_1G.eq(d_tlb.lu_is_1G_o),
                     dtlb_is_512G.eq(d_tlb.lu_is_512G_o),
                     dtlb_lu_hit.eq(d_tlb.lu_hit_o),
                    ]

        # PTW
        m.submodules.ptw = ptw = PTW(self.asid_width)
        m.d.comb += [ptw_active.eq(ptw.ptw_active_o),
                     walking_instr.eq(ptw.walking_instr_o),
                     ptw_error.eq(ptw.ptw_error_o),
                     ptw.enable_translation_i.eq(self.enable_translation_i),

                     update_vaddr.eq(ptw.update_vaddr_o),
                     update_ptw_itlb.eq(ptw.itlb_update_o),
                     update_ptw_dtlb.eq(ptw.dtlb_update_o),

                     ptw.itlb_access_i.eq(itlb_lu_access),
                     ptw.itlb_hit_i.eq(itlb_lu_hit),
                     ptw.itlb_vaddr_i.eq(self.icache_areq_i.fetch_vaddr),

                     ptw.dtlb_access_i.eq(dtlb_lu_access),
                     ptw.dtlb_hit_i.eq(dtlb_lu_hit),
                     ptw.dtlb_vaddr_i.eq(self.lsu_vaddr_i),

                     ptw.req_port_i.eq(self.req_port_i),
                     self.req_port_o.eq(ptw.req_port_o),
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

        # MMU disabled: just pass through
        m.d.comb += [self.icache_areq_o.fetch_valid.eq(
                                                self.icache_areq_i.fetch_req),
                     # play through in case we disabled address translation
                     self.icache_areq_o.fetch_paddr.eq(
                                                self.icache_areq_i.fetch_vaddr)
                    ]
        # two potential exception sources:
        # 1. HPTW threw an exception -> signal with a page fault exception
        # 2. We got an access error because of insufficient permissions ->
        #    throw an access exception
        m.d.comb += self.icache_areq_o.fetch_exception.valid.eq(0)
        # Check whether we are allowed to access this memory region
        # from a fetch perspective

        # PLATEN TODO: use PermissionValidator instead [we like modules]
        m.d.comb += iaccess_err.eq(self.icache_areq_i.fetch_req & \
                                   (((self.priv_lvl_i == PRIV_LVL_U) & \
                                      ~itlb_content.u) | \
                                   ((self.priv_lvl_i == PRIV_LVL_S) & \
                                    itlb_content.u)))

        # MMU enabled: address from TLB, request delayed until hit.
        # Error when TLB hit and no access right or TLB hit and
        # translated address not valid (e.g.  AXI decode error),
        # or when PTW performs walk due to ITLB miss and raises
        # an error.
        with m.If (self.enable_translation_i):
            # we work with SV48, so if VM is enabled, check that
            # all bits [47:38] are equal
            with m.If (self.icache_areq_i.fetch_req & \
                ~(((~self.icache_areq_i.fetch_vaddr[47:64]) == 0) | \
                 (self.icache_areq_i.fetch_vaddr[47:64]) == 0)):
                fe = self.icache_areq_o.fetch_exception
                m.d.comb += [fe.cause.eq(INSTR_ACCESS_FAULT),
                             fe.tval.eq(self.icache_areq_i.fetch_vaddr),
                             fe.valid.eq(1)
                            ]

            m.d.comb += self.icache_areq_o.fetch_valid.eq(0)

            # 4K page
            paddr = Signal.like(self.icache_areq_o.fetch_paddr)
            paddr4k = Cat(self.icache_areq_i.fetch_vaddr[0:12],
                          itlb_content.ppn)
            m.d.comb += paddr.eq(paddr4k)
            # Mega page
            with m.If(itlb_is_2M):
                m.d.comb += paddr[12:21].eq(
                          self.icache_areq_i.fetch_vaddr[12:21])
            # Giga page
            with m.If(itlb_is_1G):
                m.d.comb += paddr[12:30].eq(
                          self.icache_areq_i.fetch_vaddr[12:30])
            m.d.comb += self.icache_areq_o.fetch_paddr.eq(paddr)
            # Tera page
            with m.If(itlb_is_512G):
                m.d.comb += paddr[12:39].eq(
                          self.icache_areq_i.fetch_vaddr[12:39])
            m.d.comb += self.icache_areq_o.fetch_paddr.eq(paddr)

            # ---------
            # ITLB Hit
            # --------
            # if we hit the ITLB output the request signal immediately
            with m.If(itlb_lu_hit):
                m.d.comb += self.icache_areq_o.fetch_valid.eq(
                                          self.icache_areq_i.fetch_req)
                # we got an access error
                with m.If (iaccess_err):
                    # throw a page fault
                    fe = self.icache_areq_o.fetch_exception
                    m.d.comb += [fe.cause.eq(INSTR_ACCESS_FAULT),
                                 fe.tval.eq(self.icache_areq_i.fetch_vaddr),
                                 fe.valid.eq(1)
                                ]
            # ---------
            # ITLB Miss
            # ---------
            # watch out for exceptions happening during walking the page table
            with m.Elif(ptw_active & walking_instr):
                m.d.comb += self.icache_areq_o.fetch_valid.eq(ptw_error)
                fe = self.icache_areq_o.fetch_exception
                m.d.comb += [fe.cause.eq(INSTR_PAGE_FAULT),
                             fe.tval.eq(uaddr64),
                             fe.valid.eq(1)
                            ]

        #-----------------------
        # Data Interface
        #-----------------------

        lsu_vaddr = Signal(64)
        dtlb_pte = PTE()
        misaligned_ex = RVException()
        lsu_req = Signal()
        lsu_is_store = Signal()
        dtlb_hit = Signal()
        #dtlb_is_2M = Signal()
        #dtlb_is_1G = Signal()
        #dtlb_is_512 = Signal()

        # check if we need to do translation or if we are always
        # ready (e.g.: we are not translating anything)
        m.d.comb += self.lsu_dtlb_hit_o.eq(Mux(self.en_ld_st_translation_i,
                                          dtlb_lu_hit, 1))

        # The data interface is simpler and only consists of a
        # request/response interface
        m.d.comb += [
            # save request and DTLB response
            lsu_vaddr.eq(self.lsu_vaddr_i),
            lsu_req.eq(self.lsu_req_i),
            misaligned_ex.eq(self.misaligned_ex_i),
            dtlb_pte.eq(dtlb_content),
            dtlb_hit.eq(dtlb_lu_hit),
            lsu_is_store.eq(self.lsu_is_store_i),
            #dtlb_is_2M.eq(dtlb_is_2M),
            #dtlb_is_1G.eq(dtlb_is_1G),
            ##dtlb_is_512.eq(self.dtlb_is_512G) #????
        ]
        m.d.sync += [
            self.lsu_paddr_o.eq(lsu_vaddr),
            self.lsu_valid_o.eq(lsu_req),
            self.lsu_exception_o.eq(misaligned_ex),
        ]

        sverr = Signal()
        usrerr = Signal()

        m.d.comb += [
            # mute misaligned exceptions if there is no request
            # otherwise they will throw accidental exceptions
            misaligned_ex.valid.eq(self.misaligned_ex_i.valid & self.lsu_req_i),

            # SUM is not set and we are trying to access a user
            # page in supervisor mode
            sverr.eq(self.ld_st_priv_lvl_i == PRIV_LVL_S & ~self.sum_i & \
                       dtlb_pte.u),
            # this is not a user page but we are in user mode and
            # trying to access it
            usrerr.eq(self.ld_st_priv_lvl_i == PRIV_LVL_U & ~dtlb_pte.u),

            # Check if the User flag is set, then we may only
            # access it in supervisor mode if SUM is enabled
            daccess_err.eq(sverr | usrerr),
            ]

        # translation is enabled and no misaligned exception occurred
        with m.If(self.en_ld_st_translation_i & ~misaligned_ex.valid):
            m.d.comb += lsu_req.eq(0)
            # 4K page
            paddr = Signal.like(lsu_vaddr)
            paddr4k = Cat(lsu_vaddr[0:12], itlb_content.ppn)
            m.d.comb += paddr.eq(paddr4k)
            # Mega page
            with m.If(dtlb_is_2M):
                m.d.comb += paddr[12:21].eq(lsu_vaddr[12:21])
            # Giga page
            with m.If(dtlb_is_1G):
                m.d.comb += paddr[12:30].eq(lsu_vaddr[12:30])
            m.d.sync += self.lsu_paddr_o.eq(paddr)
            # TODO platen tera_page

            # ---------
            # DTLB Hit
            # --------
            with m.If(dtlb_hit & lsu_req):
                m.d.comb += lsu_req.eq(1)
                # this is a store
                with m.If (lsu_is_store):
                    # check if the page is write-able and
                    # we are not violating privileges
                    # also check if the dirty flag is set
                    with m.If(~dtlb_pte.w | daccess_err | ~dtlb_pte.d):
                        le = self.lsu_exception_o
                        m.d.sync += [le.cause.eq(STORE_PAGE_FAULT),
                                     le.tval.eq(lsu_vaddr),
                                     le.valid.eq(1)
                                    ]

                # this is a load, check for sufficient access
                # privileges - throw a page fault if necessary
                with m.Elif(daccess_err):
                    le = self.lsu_exception_o
                    m.d.sync += [le.cause.eq(LOAD_PAGE_FAULT),
                                 le.tval.eq(lsu_vaddr),
                                 le.valid.eq(1)
                                ]
            # ---------
            # DTLB Miss
            # ---------
            # watch out for exceptions
            with m.Elif (ptw_active & ~walking_instr):
                # page table walker threw an exception
                with m.If (ptw_error):
                    # an error makes the translation valid
                    m.d.comb += lsu_req.eq(1)
                    # the page table walker can only throw page faults
                    with m.If (lsu_is_store):
                        le = self.lsu_exception_o
                        m.d.sync += [le.cause.eq(STORE_PAGE_FAULT),
                                     le.tval.eq(uaddr64),
                                     le.valid.eq(1)
                                    ]
                    with m.Else():
                        m.d.sync += [le.cause.eq(LOAD_PAGE_FAULT),
                                     le.tval.eq(uaddr64),
                                     le.valid.eq(1)
                                    ]

        return m

    def ports(self):
        return [self.flush_i, self.enable_translation_i,
                self.en_ld_st_translation_i,
                self.lsu_req_i,
                self.lsu_vaddr_i, self.lsu_is_store_i, self.lsu_dtlb_hit_o,
                self.lsu_valid_o, self.lsu_paddr_o,
                self.priv_lvl_i, self.ld_st_priv_lvl_i, self.sum_i, self.mxr_i,
                self.satp_ppn_i, self.asid_i, self.flush_tlb_i,
                self.itlb_miss_o, self.dtlb_miss_o] + \
                self.icache_areq_i.ports() + self.icache_areq_o.ports() + \
                self.req_port_i.ports() + self.req_port_o.ports() + \
                self.misaligned_ex_i.ports() + self.lsu_exception_o.ports()

if __name__ == '__main__':
    mmu = MMU()
    vl = rtlil.convert(mmu, ports=mmu.ports())
    with open("test_mmu.il", "w") as f:
        f.write(vl)

