from math import log2
from nmigen import Signal, Module, Cat, Const

from ptw import TLBUpdate, PTE, ASID_WIDTH

class PLRU:
    """ PLRU - Pseudo Least Recently Used Replacement

        PLRU-tree indexing:
        lvl0        0
                   / \
                  /   \
        lvl1     1     2
                / \   / \
        lvl2   3   4 5   6
              / \ /\/\  /\
             ... ... ... ...
    """
    def __init__(self, entries):
        self.entries = entries
        self.lu_hit = Signal(entries)
        self.replace_en_o = Signal(entries)
        self.lu_access_i = Signal()
        # Tree (bit per entry)
        TLBSZ = 2*(self.entries-1)
        self.plru_tree = Signal(TLBSZ)

    def elaborate(self, platform):
        m = Module()

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
        LOG_TLB = int(log2(self.entries))
        print(LOG_TLB)
        for i in range(self.entries):
            # we got a hit so update the pointer as it was least recently used
            hit = Signal(reset_less=True)
            m.d.comb += hit.eq(self.lu_hit[i] & self.lu_access_i)
            with m.If(hit):
                # Set the nodes to the values we would expect
                for lvl in range(LOG_TLB):
                    idx_base = (1<<lvl)-1
                    # lvl0 <=> MSB, lvl1 <=> MSB-1, ...
                    shift = LOG_TLB - lvl;
                    new_idx = Const(~((i >> (shift-1)) & 1), (1, False))
                    plru_idx = idx_base + (i >> shift)
                    print ("plru", i, lvl, hex(idx_base),
                                  plru_idx, shift, new_idx)
                    m.d.sync += self.plru_tree[plru_idx].eq(new_idx)

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
        replace = []
        for i in range(self.entries):
            en = []
            for lvl in range(LOG_TLB):
                idx_base = (1<<lvl)-1
                # lvl0 <=> MSB, lvl1 <=> MSB-1, ...
                shift = LOG_TLB - lvl;
                new_idx = (i >> (shift-1)) & 1;
                plru_idx = idx_base + (i>>shift)
                plru = Signal(reset_less=True,
                              name="plru-%d-%d-%d" % (i, lvl, plru_idx))
                m.d.comb += plru.eq(self.plru_tree[plru_idx])
                # en &= plru_tree_q[idx_base + (i>>shift)] == new_idx;
                if new_idx:
                    en.append(~plru) # yes inverted (using bool())
                else:
                    en.append(plru)  # yes inverted (using bool())
            print ("plru", i, en)
            # boolean logic manipulation:
            # plru0 & plru1 & plru2 == ~(~plru0 | ~plru1 | ~plru2)
            replace.append(~Cat(*en).bool())
        m.d.comb += self.replace_en_o.eq(Cat(*replace))

        return m