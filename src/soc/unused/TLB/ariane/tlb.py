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
# Description: Translation Lookaside Buffer, SV48
#              fully set-associative

Implementation in c++:
https://raw.githubusercontent.com/Tony-Hu/TreePLRU/master/TreePLRU.cpp

Text description:
https://people.cs.clemson.edu/~mark/464/p_lru.txt

Online simulator:
http://www.ntu.edu.sg/home/smitha/ParaCache/Paracache/vm.html
"""
from math import log2
from nmigen import Signal, Module, Cat, Const, Array, Elaboratable
from nmigen.cli import verilog, rtlil
from nmigen.lib.coding import Encoder

from soc.TLB.ariane.ptw import TLBUpdate, PTE, ASID_WIDTH
from soc.TLB.ariane.plru import PLRU
from soc.TLB.ariane.tlb_content import TLBContent

TLB_ENTRIES = 8


class TLB(Elaboratable):
    def __init__(self, tlb_entries=8, asid_width=8):
        self.tlb_entries = tlb_entries
        self.asid_width = asid_width

        self.flush_i = Signal()  # Flush signal
        # Lookup signals
        self.lu_access_i = Signal()
        self.lu_asid_i = Signal(self.asid_width)
        self.lu_vaddr_i = Signal(64)
        self.lu_content_o = PTE()
        self.lu_is_2M_o = Signal()
        self.lu_is_1G_o = Signal()
        self.lu_is_512G_o = Signal()
        self.lu_hit_o = Signal()
        # Update TLB
        self.pte_width = len(self.lu_content_o.flatten())
        self.update_i = TLBUpdate(asid_width)

    def elaborate(self, platform):
        m = Module()

        vpn3 = Signal(9)  # FIXME unused signal
        vpn2 = Signal(9)
        vpn1 = Signal(9)
        vpn0 = Signal(9)

        # -------------
        # Translation
        # -------------

        # SV48 defines four levels of page tables
        m.d.comb += [vpn0.eq(self.lu_vaddr_i[12:21]),
                     vpn1.eq(self.lu_vaddr_i[21:30]),
                     vpn2.eq(self.lu_vaddr_i[30:39]),
                     vpn3.eq(self.lu_vaddr_i[39:48]),  # FIXME
                     ]

        tc = []
        for i in range(self.tlb_entries):
            tlc = TLBContent(self.pte_width, self.asid_width)
            setattr(m.submodules, "tc%d" % i, tlc)
            tc.append(tlc)
            # connect inputs
            tlc.update_i = self.update_i     # saves a lot of graphviz links
            m.d.comb += [tlc.vpn0.eq(vpn0),
                         tlc.vpn1.eq(vpn1),
                         tlc.vpn2.eq(vpn2),
                         # TODO 4th
                         tlc.flush_i.eq(self.flush_i),
                         # tlc.update_i.eq(self.update_i),
                         tlc.lu_asid_i.eq(self.lu_asid_i)]
        tc = Array(tc)

        # --------------
        # Select hit
        # --------------

        # use Encoder to select hit index
        # XXX TODO: assert that there's only one valid entry (one lu_hit)
        hitsel = Encoder(self.tlb_entries)
        m.submodules.hitsel = hitsel

        hits = []
        for i in range(self.tlb_entries):
            hits.append(tc[i].lu_hit_o)
        m.d.comb += hitsel.i.eq(Cat(*hits))  # (goes into plru as well)
        idx = hitsel.o

        active = Signal(reset_less=True)
        m.d.comb += active.eq(~hitsel.n)
        with m.If(active):
            # active hit, send selected as output
            m.d.comb += [self.lu_is_512G_o.eq(tc[idx].lu_is_512G_o),
                         self.lu_is_1G_o.eq(tc[idx].lu_is_1G_o),
                         self.lu_is_2M_o.eq(tc[idx].lu_is_2M_o),
                         self.lu_hit_o.eq(1),
                         self.lu_content_o.flatten().eq(tc[idx].lu_content_o),
                         ]

        # --------------
        # PLRU.
        # --------------

        p = PLRU(self.tlb_entries)
        plru_tree = Signal(p.TLBSZ)
        m.submodules.plru = p

        # connect PLRU inputs/outputs
        # XXX TODO: assert that there's only one valid entry (one replace_en)
        en = []
        for i in range(self.tlb_entries):
            en.append(tc[i].replace_en_i)
        m.d.comb += [Cat(*en).eq(p.replace_en_o),  # output from PLRU into tags
                     p.lu_hit.eq(hitsel.i),
                     p.lu_access_i.eq(self.lu_access_i),
                     p.plru_tree.eq(plru_tree)]
        m.d.sync += plru_tree.eq(p.plru_tree_o)

        # --------------
        # Sanity checks
        # --------------

        assert (self.tlb_entries % 2 == 0) and (self.tlb_entries > 1), \
            "TLB size must be a multiple of 2 and greater than 1"
        assert (self.asid_width >= 1), \
            "ASID width must be at least 1"

        return m

        """
        # Just for checking
        function int countSetBits(logic[self.tlb_entries-1:0] vector);
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
                self.lu_is_2M_o, self.lu_1G_o, self.lu_is_512G_o, self.lu_hit_o
                ] + self.lu_content_o.ports() + self.update_i.ports()


if __name__ == '__main__':
    tlb = TLB()
    vl = rtlil.convert(tlb, ports=tlb.ports())
    with open("test_tlb.il", "w") as f:
        f.write(vl)
