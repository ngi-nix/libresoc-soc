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
# Date: 21.4.2017
# Description: Translation Lookaside Buffer, SV39
#              fully set-associative
"""
from math import log2
from nmigen import Signal, Module, Cat, Const, Array
from nmigen.cli import verilog, rtlil


# SV39 defines three levels of page tables
class TLBEntry:
    def __init__(self):
        self.asid = Signal(ASID_WIDTH)
        self.vpn2 = Signal(9)
        self.vpn1 = Signal(9)
        self.vpn0 = Signal(9)
        self.is_2M = Signal()
        self.is_1G = Signal()
        self.valid = Signal()

TLB_ENTRIES = 4
ASID_WIDTH  = 1

from ptw import TLBUpdate, PTE


class TLB:
    def __init__(self):
        self.flush_i = Signal()  # Flush signal
        # Update TLB
        self.update_i = TLBUpdate()
        # Lookup signals
        self.lu_access_i = Signal()
        self.lu_asid_i = Signal(ASID_WIDTH)
        self.lu_vaddr_i = Signal(64)
        self.lu_content_o = PTE()
        self.lu_is_2M_o = Signal()
        self.lu_is_1G_o = Signal()
        self.lu_hit_o = Signal()

    def elaborate(self, platform):
        m = Module()

        # SV39 defines three levels of page tables
        tags = Array([TLBEntry() for i in range(TLB_ENTRIES)])
        content = Array([PTE() for i in range(TLB_ENTRIES)])

        vpn2 = Signal(9)
        vpn1 = Signal(9)
        vpn0 = Signal(9)
        lu_hit = Signal(TLB_ENTRIES)     # to replacement logic
        replace_en = Signal(TLB_ENTRIES) # replace the following entry,
                                         # set by replacement strategy
        #-------------
        # Translation
        #-------------
        m.d.comb += [ vpn0.eq(self.lu_vaddr_i[12:21]),
                      vpn1.eq(self.lu_vaddr_i[21:30]),
                      vpn2.eq(self.lu_vaddr_i[30:39]),
                    ]

        for i in range(TLB_ENTRIES):
            m.d.comb += lu_hit[i].eq(0)
            # temporaries for 1st level match
            asid_ok = Signal()
            vpn2_ok = Signal()
            tags_ok = Signal()
            vpn2_hit = Signal()
            m.d.comb += [tags_ok.eq(tags[i].valid),
                         asid_ok.eq(tags[i].asid == self.lu_asid_i),
                         vpn2_ok.eq(tags[i].vpn2 == vpn2),
                         vpn2_hit.eq(tags_ok & asid_ok & vpn2_ok)]
            # temporaries for 2nd level match
            vpn1_ok = Signal()
            tags_2M = Signal()
            vpn0_ok = Signal()
            vpn0_or_2M = Signal()
            m.d.comb += [vpn1_ok.eq(vpn1 == tags[i].vpn1),
                         tags_2M.eq(tags[i].is_2M),
                         vpn0_ok.eq(vpn0 == tags[i].vpn0),
                         vpn0_or_2M.eq(tags_2M | vpn0_ok)]
            # first level match, this may be a giga page,
            # check the ASID flags as well
            with m.If(vpn2_hit):
                # second level
                with m.If (tags[i].is_1G):
                    m.d.sync += self.lu_content_o.eq(content[i])
                    m.d.comb += [ self.lu_is_1G_o.eq(1),
                                  self.lu_hit_o.eq(1),
                                  lu_hit[i].eq(1),
                                ]
                # not a giga page hit so check further
                with m.Elif(vpn1_ok):
                    # this could be a 2 mega page hit or a 4 kB hit
                    # output accordingly
                    with m.If(vpn0_or_2M):
                        m.d.sync += self.lu_content_o.eq(content[i])
                        m.d.comb += [ self.lu_is_2M_o.eq(tags[i].is_2M),
                                      self.lu_hit_o.eq(1),
                                      lu_hit[i].eq(1),
                                    ]

        # ------------------
        # Update and Flush
        # ------------------

        for i in range(TLB_ENTRIES):
            replace_valid = Signal()
            m.d.comb += replace_valid.eq(self.update_i.valid & replace_en[i])
            with m.If (self.flush_i):
                # invalidate (flush) conditions: all if zero or just this ASID
                with m.If (self.lu_asid_i == Const(0, ASID_WIDTH) |
                          (self.lu_asid_i == tags[i].asid)):
                    m.d.sync += tags[i].valid.eq(0)

            # normal replacement
            with m.Elif(replace_valid):
                m.d.sync += [ # update tag array
                              tags[i].asid.eq(self.update_i.asid),
                              tags[i].vpn2.eq(self.update_i.vpn[18:27]),
                              tags[i].vpn1.eq(self.update_i.vpn[9:18]),
                              tags[i].vpn0.eq(self.update_i.vpn[0:9]),
                              tags[i].is_1G.eq(self.update_i.is_1G),
                              tags[i].is_2M.eq(self.update_i.is_2M),
                              tags[i].valid.eq(1),
                              # and content as well
                              content[i].eq(self.update_i.content)
                            ]

        # -----------------------------------------------
        # PLRU - Pseudo Least Recently Used Replacement
        # -----------------------------------------------

        TLBSZ = 2*(TLB_ENTRIES-1)
        plru_tree = Signal(TLBSZ)

        # The PLRU-tree indexing:
        # lvl0        0
        #            / \
        #           /   \
        # lvl1     1     2
        #         / \   / \
        # lvl2   3   4 5   6
        #       / \ /\/\  /\
        #      ... ... ... ...
        # Just predefine which nodes will be set/cleared
        # E.g. for a TLB with 8 entries, the for-loop is semantically
        # equivalent to the following pseudo-code:
        # unique case (1'b1)
        # lu_hit[7]: plru_tree[0, 2, 6] = {1, 1, 1};
        # lu_hit[6]: plru_tree[0, 2, 6] = {1, 1, 0};
        # lu_hit[5]: plru_tree[0, 2, 5] = {1, 0, 1};
        # lu_hit[4]: plru_tree[0, 2, 5] = {1, 0, 0};
        # lu_hit[3]: plru_tree[0, 1, 4] = {0, 1, 1};
        # lu_hit[2]: plru_tree[0, 1, 4] = {0, 1, 0};
        # lu_hit[1]: plru_tree[0, 1, 3] = {0, 0, 1};
        # lu_hit[0]: plru_tree[0, 1, 3] = {0, 0, 0};
        # default: begin /* No hit */ end
        # endcase
        LOG_TLB = int(log2(TLB_ENTRIES))
        for i in range(TLB_ENTRIES):
            # we got a hit so update the pointer as it was least recently used
            hit = Signal()
            m.d.comb += hit.eq(lu_hit[i] & self.lu_access_i)
            with m.If(hit):
                # Set the nodes to the values we would expect
                for lvl in range(LOG_TLB):
                    idx_base = (1<<lvl)-1
                    # lvl0 <=> MSB, lvl1 <=> MSB-1, ...
                    shift = LOG_TLB - lvl;
                    new_idx = Const(~((i >> (shift-1)) & 1), 1)
                    print ("plru", i, lvl, hex(idx_base), shift, new_idx)
                    m.d.sync += plru_tree[idx_base + (i >> shift)].eq(new_idx)

        # Decode tree to write enable signals
        # Next for-loop basically creates the following logic for e.g.
        # an 8 entry TLB (note: pseudo-code obviously):
        # replace_en[7] = &plru_tree[ 6, 2, 0]; #plru_tree[0,2,6]=={1,1,1}
        # replace_en[6] = &plru_tree[~6, 2, 0]; #plru_tree[0,2,6]=={1,1,0}
        # replace_en[5] = &plru_tree[ 5,~2, 0]; #plru_tree[0,2,5]=={1,0,1}
        # replace_en[4] = &plru_tree[~5,~2, 0]; #plru_tree[0,2,5]=={1,0,0}
        # replace_en[3] = &plru_tree[ 4, 1,~0]; #plru_tree[0,1,4]=={0,1,1}
        # replace_en[2] = &plru_tree[~4, 1,~0]; #plru_tree[0,1,4]=={0,1,0}
        # replace_en[1] = &plru_tree[ 3,~1,~0]; #plru_tree[0,1,3]=={0,0,1}
        # replace_en[0] = &plru_tree[~3,~1,~0]; #plru_tree[0,1,3]=={0,0,0}
        # For each entry traverse the tree. If every tree-node matches
        # the corresponding bit of the entry's index, this is
        # the next entry to replace.
        for i in range(TLB_ENTRIES):
            en = Signal(LOG_TLB)
            for lvl in range(LOG_TLB):
                idx_base = (1<<lvl)-1
                # lvl0 <=> MSB, lvl1 <=> MSB-1, ...
                shift = LOG_TLB - lvl;
                new_idx = (i >> (shift-1)) & 1;
                plru = Signal()
                m.d.comb += plru.eq(plru_tree[idx_base + (i>>shift)])
                # en &= plru_tree_q[idx_base + (i>>shift)] == new_idx;
                if new_idx:
                    en[lvl].eq(~plru) # yes inverted (using bool())
                else:
                    en[lvl].eq(plru)  # yes inverted (using bool())
            print ("plru", i, en)
            # boolean logic manipluation:
            # plur0 & plru1 & plur2 == ~(~plru0 | ~plru1 | ~plru2)
            m.d.sync += replace_en[i].eq(~Cat(*en).bool())

        #--------------
        # Sanity checks
        #--------------

        assert (TLB_ENTRIES % 2 == 0) and (TLB_ENTRIES > 1), \
            "TLB size must be a multiple of 2 and greater than 1"
        assert (ASID_WIDTH >= 1), \
            "ASID width must be at least 1"

        return m

        """
        # Just for checking
        function int countSetBits(logic[TLB_ENTRIES-1:0] vector);
          automatic int count = 0;
          foreach (vector[idx]) begin
            count += vector[idx];
          end
          return count;
        endfunction

        assert property (@(posedge clk_i)(countSetBits(lu_hit) <= 1))
          else $error("More then one hit in TLB!"); $stop(); end
        assert property (@(posedge clk_i)(countSetBits(replace_en) <= 1))
          else $error("More then one TLB entry selected for next replace!");
        """

    def ports(self):
        return [self.flush_i, self.lu_access_i,
                 self.lu_asid_i, self.lu_vaddr_i,
                 self.lu_is_2M_o, self.lu_is_1G_o, self.lu_hit_o,
                ] + self.lu_content_o.ports() + self.update_i.ports()

if __name__ == '__main__':
    tlb = TLB()
    vl = rtlil.convert(tlb, ports=tlb.ports())
    with open("test_tlb.il", "w") as f:
        f.write(vl)

