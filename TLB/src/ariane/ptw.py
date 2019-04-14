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
# Author: David Schaffenrath, TU Graz
# Author: Florian Zaruba, ETH Zurich
# Date: 24.4.2017
# Description: Hardware-PTW

/* verilator lint_off WIDTH */
import ariane_pkg::*;
"""

from nmigen import Const, Signal, Cat
from nmigen.hdl.ast import ArrayProxy
from math import log

DCACHE_SET_ASSOC = 8
CONFIG_L1D_SIZE =  32*1024
DCACHE_INDEX_WIDTH = int(log(CONFIG_L1D_SIZE / DCACHE_SET_ASSOC))
DCACHE_TAG_WIDTH = 56 - DCACHE_INDEX_WIDTH

class DCacheReqI:
    def __init__(self):
        self.address_index = Signal(DCACHE_INDEX_WIDTH)
        self.address_tag = Signal(DCACHE_TAG_WIDTH)
        self.data_wdata = Signal(64)
        self.data_req = Signal()
        self.data_we = Signal()
        self.data_be = Signal(8)
        self.data_size = Signal(2)
        self.kill_req = Signal()
        self.tag_valid = Signal()


class DCacheReqO:
    def __init__(self):
        data_gnt = Signal()
        data_rvalid = Signal()
        data_rdata = Signal(64)

ASID_WIDTH = 8

class PTE: #(RecordObject):
    def __init__(self):
        self.reserved = Signal(10)
        self.ppn = Signal(44)
        self.rsw = Signal(2)
        self.d = Signal()
        self.a = Signal()
        self.g = Signal()
        self.u = Signal()
        self.x = Signal()
        self.w = Signal()
        self.r = Signal()
        self.v = Signal()

    def flatten(self):
        return Cat(*self.ports())

    def eq(self, x):
        if isinstance(x, ArrayProxy):
            res = []
            for o in self.ports():
                i = getattr(x, o.name)
                res.append(i)
            x = Cat(*res)
        else:
            x = x.flatten()
        return self.flatten().eq(x)

    def ports(self):
        return [self.reserved, self.ppn, self.rsw, self.d, self.a, self.g,
                self.u, self.x, self.w, self.r, self.v]


class TLBUpdate:
    def __init__(self):
        self.valid = Signal()      # valid flag
        self.is_2M = Signal()
        self.is_1G = Signal()
        self.vpn = Signal(27)
        self.asid = Signal(ASID_WIDTH)
        self.content = PTE()

    def flatten(self):
        return Cat(*self.ports())

    def eq(self, x):
        return self.flatten().eq(x.flatten())

    def ports(self):
        return [self.valid, self.is_2M, self.is_1G, self.vpn, self.asid] + \
                self.content.ports()

# SV39 defines three levels of page tables
LVL1 = Const(0, 2)
LVL2 = Const(1, 2)
LVL3 = Const(2, 2)


class PTW:
    def __init__(self):
        flush_i = Signal() # flush everything, we need to do this because
        # actually everything we do is speculative at this stage
        # e.g.: there could be a CSR instruction that changes everything
        ptw_active_o = Signal()
        walking_instr_o = Signal()        # set when walking for TLB
        ptw_error_o = Signal()            # set when an error occurred
        enable_translation_i = Signal()   # CSRs indicate to enable SV39
        en_ld_st_translation_i = Signal() # enable VM translation for ld/st

        lsu_is_store_i = Signal() ,       # this translation triggered by store
        # PTW memory interface
        req_port_i = DCacheReqO()
        req_port_o = DCacheReqI()

        # to TLBs, update logic
        itlb_update_o = TLBUpdate()
        dtlb_update_o = TLBUpdate()

        update_vaddr_o = Signal(39)

        asid_i = Signal(ASID_WIDTH)
        # from TLBs
        # did we miss?
        itlb_access_i = Signal()
        itlb_hit_i = Signal()
        itlb_vaddr_i = Signal(64)

        dtlb_access_i = Signal()
        dtlb_hit_i = Signal()
        dtlb_vaddr_i = Signal(64)
        # from CSR file
        satp_ppn_i = Signal(44) # ppn from satp
        mxr_i = Signal()
        # Performance counters
        itlb_miss_o = Signal()
        dtlb_miss_o = Signal()


        # input registers
        data_rvalid = Signal()
        data_rdata = Signal(64)

        pte = PTE()
        m.d.comb += pte.eq(data_rdata)

        ptw_lvl = Signal(2, reset=LVL1)

        # is this an instruction page table walk?
        is_instr_ptw = Signal()
        global_mapping = Signal()
        # latched tag signal
        tag_valid = Signal()
        # register the ASID
        tlb_update_asid = Signal(ASID_WIDTH)
        # register VPN we need to walk, SV39 defines a 39 bit virtual addr
        vaddr = Signal(64)
        # 4 byte aligned physical pointer
        ptw_pptr = Signal(56)

        end = DCACHE_INDEX_WIDTH + DCACHE_TAG_WIDTH
        m.d.sync += [
            # Assignments
            update_vaddr_o.eq(vaddr),

            ptw_active_o.eq(state != IDLE),
            walking_instr_o.eq(is_instr_ptw),
            # directly output the correct physical address
            req_port_o.address_index.eq(ptw_pptr[0:DCACHE_INDEX_WIDTH]),
            req_port_o.address_tag.eq(ptw_pptr[DCACHE_INDEX_WIDTH:end]),
            # we are never going to kill this request
            req_port_o.kill_req.eq(0),
            # we are never going to write with the HPTW
            req_port_o.data_wdata.eq(Const(0, 64)),
            # -----------
            # TLB Update
            # -----------
            itlb_update_o.vpn.eq(vaddr[12:39]),
            dtlb_update_o.vpn.eq(vaddr[12:39]),
            # update the correct page table level
            itlb_update_o.is_2M.eq(ptw_lvl == LVL2),
            itlb_update_o.is_1G.eq(ptw_lvl == LVL1),
            dtlb_update_o.is_2M.eq(ptw_lvl == LVL2),
            dtlb_update_o.is_1G.eq(ptw_lvl == LVL1),
            # output the correct ASID
            itlb_update_o.asid.eq(tlb_update_asid),
            dtlb_update_o.asid.eq(tlb_update_asid),
            # set the global mapping bit
            itlb_update_o.content.eq(pte | (global_mapping << 5)),
            dtlb_update_o.content.eq(pte | (global_mapping << 5)),

        ]
        m.d.comb += [
            req_port_o.tag_valid.eq(tag_valid),
        ]
        #-------------------
        # Page table walker
        #-------------------
        # A virtual address va is translated into a physical address pa as
        # follows:
        # 1. Let a be sptbr.ppn × PAGESIZE, and let i = LEVELS-1. (For Sv39,
        #    PAGESIZE=2^12 and LEVELS=3.)
        # 2. Let pte be the value of the PTE at address a+va.vpn[i]×PTESIZE.
        #    (For Sv32, PTESIZE=4.)
        # 3. If pte.v = 0, or if pte.r = 0 and pte.w = 1, stop and raise an
        #    access exception.
        # 4. Otherwise, the PTE is valid. If pte.r = 1 or pte.x = 1, go to
        #    step 5.  Otherwise, this PTE is a pointer to the next level of
        #    the page table.
        #    Let i=i-1. If i < 0, stop and raise an access exception.
        #    Otherwise, let a = pte.ppn × PAGESIZE and go to step 2.
        # 5. A leaf PTE has been found. Determine if the requested memory
        #    access is allowed by the pte.r, pte.w, and pte.x bits. If not,
        #    stop and raise an access exception. Otherwise, the translation is
        #    successful.  Set pte.a to 1, and, if the memory access is a
        #    store, set pte.d to 1.
        #    The translated physical address is given as follows:
        #      - pa.pgoff = va.pgoff.
        #      - If i > 0, then this is a superpage translation and
        #        pa.ppn[i-1:0] = va.vpn[i-1:0].
        #      - pa.ppn[LEVELS-1:i] = pte.ppn[LEVELS-1:i].
        # 6. If i > 0 and pa.ppn[i − 1 : 0] != 0, this is a misaligned
        #    superpage stop and raise a page-fault exception.

        m.d.sync += tag_valid.eq(0)

        # default assignments
        m.d.comb += [
            # PTW memory interface
            req_port_o.data_req.eq(0),
            req_port_o.data_be.eq(Const(0xFF, 8)),
            req_port_o.data_size.eq(Const(0b11, 2)),
            req_port_o.data_we.eq(0),
            ptw_error_o.eq(0),
            itlb_update_o.valid.eq(0),
            dtlb_update_o.valid.eq(0),

            itlb_miss_o.eq(0),
            dtlb_miss_o.eq(0),
        ]

        with m.FSM() as fsm:

            with m.State("IDLE"):
                # by default we start with the top-most page table
                m.d.sync += [is_instr_ptw.eq(0),
                             ptw_lvl.eq(LVL1),
                             global_mapping.eq(0),
                            ]
                # we got an ITLB miss?
                with m.If(enable_translation_i & itlb_access_i & \
                          ~itlb_hit_i & ~dtlb_access_i):
                    pptr = Cat(Const(0, 3), itlb_vaddr_i[30:39], satp_ppn_i)
                    m.d.sync += [ptw_pptr.eq(pptr),
                                is_instr_ptw.eq(1),
                                 vaddr.eq(itlb_vaddr_i),
                                tlb_update_asid.eq(asid_i),
                                ]
                    m.d.comb += [itlb_miss_o.eq(1)]
                    m.next = "WAIT_GRANT"
                # we got a DTLB miss?
                with m.Elif(en_ld_st_translation_i & dtlb_access_i & \
                            ~dtlb_hit_i):
                    pptr = Cat(Const(0, 3), dtlb_vaddr_i[30:39], satp_ppn_i)
                    m.d.sync += [ptw_pptr.eq(pptr),
                                 vaddr.eq(dtlb_vaddr_i),
                                 tlb_update_asid.eq(asid_i),
                                ]
                    m.d.comb += [ dtlb_miss_o.eq(1)]
                    m.next = "WAIT_GRANT"

            with m.State("WAIT_GRANT"):
                # send a request out
                m.d.comb += req_port_o.data_req.eq(1)
                # wait for the WAIT_GRANT
                with m.If(req_port_i.data_gnt):
                    # send the tag valid signal one cycle later
                    m.d.sync += tag_valid.eq(1)
                    m.next = "PTE_LOOKUP"

            with m.State("PTE_LOOKUP"):
                # we wait for the valid signal
                with m.If(data_rvalid):

                    # check if the global mapping bit is set
                    with m.If (pte.g):
                        m.d.sync += global_mapping.eq(1)

                    # -------------
                    # Invalid PTE
                    # -------------
                    # If pte.v = 0, or if pte.r = 0 and pte.w = 1,
                    # stop and raise a page-fault exception.
                    with m.If (~pte.v | (~pte.r & pte.w)):
                        m.next = "PROPAGATE_ERROR"
                    # -----------
                    # Valid PTE
                    # -----------
                    with m.Else():
                        m.next = "IDLE"
                        # it is a valid PTE
                        # if pte.r = 1 or pte.x = 1 it is a valid PTE
                        with m.If (pte.r | pte.x):
                            # Valid translation found (either 1G, 2M or 4K entry)
                            with m.If(is_instr_ptw):
                                # ------------
                                # Update ITLB
                                # ------------
                                # If page is not executable, we can
                                # directly raise an error. This
                                # doesn't put a useless entry into
                                # the TLB. The same idea applies
                                # to the access flag since we let
                                # the access flag be managed by SW.
                                with m.If (~pte.x | ~pte.a):
                                    m.next = "IDLE"
                                with m.Else():
                                    m.d.comb += itlb_update_o.valid.eq(1)

                            with m.Else():
                                # ------------
                                # Update DTLB
                                # ------------
                                # Check if the access flag has been set,
                                # otherwise throw a page-fault
                                # and let the software handle those bits.
                                # If page is not readable (there are
                                # no write-only pages)
                                # we can directly raise an error. This
                                # doesn't put a useless
                                # entry into the TLB.
                                with m.If(pte.a & (pte.r | (pte.x & mxr_i))):
                                    m.d.comb += dtlb_update_o.valid.eq(1)
                                with m.Else():
                                    m.next = "PROPAGATE_ERROR"
                                # Request is a store: perform some
                                # additional checks
                                # If the request was a store and the
                                # page is not write-able, raise an error
                                # the same applies if the dirty flag is not set
                                with m.If (lsu_is_store_i & (~pte.w | ~pte.d)):
                                    m.d.comb += dtlb_update_o.valid.eq(0)
                                    m.next = "PROPAGATE_ERROR"

                            # check if the ppn is correctly aligned: Case (6)
                            l1err = Signal()
                            l2err = Signal()
                            m.d.comb += [l2err.eq((ptw_lvl == LVL2) & \
                                           pte.ppn[0:9] != Const(0, 9)),
                                         l1err.eq((ptw_lvl == LVL1) & \
                                           pte.ppn[0:18] != Const(0, 18))
                                        ]
                            with m.If(l1err | l2err):
                                m.next = "PROPAGATE_ERROR"
                                m.d.comb += [dtlb_update_o.valid.eq(0),
                                             itlb_update_o.valid.eq(0)]

                        # this is a pointer to the next TLB level
                        with m.Else():
                            # pointer to next level of page table
                            with m.If (ptw_lvl == LVL1):
                                # we are in the second level now
                                pptr = Cat(Const(0, 3), dtlb_vaddr_i[21:30],
                                           pte.ppn)
                                m.d.sync += [ptw_pptr.eq(pptr),
                                            ptw_lvl.eq(LVL2)]
                            with m.If(ptw_lvl == LVL2):
                                # here we received a pointer to the third level
                                pptr = Cat(Const(0, 3), dtlb_vaddr_i[12:21],
                                           pte.ppn)
                                m.d.sync += [ptw_pptr.eq(pptr),
                                            ptw_lvl.eq(LVL3)
                                            ]
                            m.next = "WAIT_GRANT"

                            with m.If (ptw_lvl == LVL3):
                                # Should already be the last level
                                # page table => Error
                                m.d.sync += ptw_lvl.eq(LVL3)
                                m.next = "PROPAGATE_ERROR"
                # we've got a data WAIT_GRANT so tell the
                # cache that the tag is valid

            # Propagate error to MMU/LSU
            with m.State("PROPAGATE_ERROR"):
                m.next = "IDLE"
                m.d.comb += ptw_error_o.eq(1)

            # wait for the rvalid before going back to IDLE
            with m.State("WAIT_RVALID"):
                with m.If(data_rvalid):
                    m.next = "IDLE"

        # -------
        # Flush
        # -------
        # should we have flushed before we got an rvalid,
        # wait for it until going back to IDLE
        with m.If(flush_i):
            # on a flush check whether we are
            # 1. in the PTE Lookup check whether we still need to wait
            #    for an rvalid
            # 2. waiting for a grant, if so: wait for it
            # if not, go back to idle
            with m.If (((state == PTE_LOOKUP) & ~data_rvalid) | \
                       ((state == WAIT_GRANT) & req_port_i.data_gnt)):
                m.next = "WAIT_RVALID"
            with m.Else():
                m.next = "IDLE"

        m.d.sync += [data_rdata.eq(req_port_i.data_rdata),
                     data_rvalid.eq(req_port_i.data_rvalid)
                    ]

"""
if __name__ == '__main__':
    dut = PTE()
    ports = [dut.p.i_valid, dut.n.i_ready,
             dut.n.o_valid, dut.p.o_ready] + \
             [dut.p.i_data] + [dut.n.o_data]
    vl = rtlil.convert(dut, ports=ports)
    with open("test_bufunbuf999.il", "w") as f:
        f.write(vl)
"""
