# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2020, 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2021 Tobias Platen
# Funded by NLnet http://nlnet.nl
"""core of the python-based POWER9 simulator

this is part of a cycle-accurate POWER9 simulator.  its primary purpose is
not speed, it is for both learning and educational purposes, as well as
a method of verifying the HDL.

related bugs:

* https://bugs.libre-soc.org/show_bug.cgi?id=604
"""

from nmigen.back.pysim import Settle
from copy import copy
from soc.decoder.selectable_int import (FieldSelectableInt, SelectableInt,
                                        selectconcat)
from soc.decoder.helpers import exts, gtu, ltu, undefined
from soc.decoder.isa.mem import Mem

import math
import sys

# very quick, TODO move to SelectableInt utils later
def genmask(shift, size):
    res = SelectableInt(0, size)
    for i in range(size):
        if i < shift:
            res[size-1-i] = SelectableInt(1, 1)
    return res

# NOTE: POWER 3.0B annotation order!  see p4 1.3.2
# MSB is indexed **LOWEST** (sigh)
# from gem5 radixwalk.hh
# Bitfield<63> valid;  64 - (63 + 1) = 0
# Bitfield<62> leaf;   64 - (62 + 1) = 1

def rpte_valid(r):
    return bool(r[0])

def rpte_leaf(r):
    return bool(r[1])

def NLB(x):
    """
    Next Level Base
    right shifted by 8
    """
    return x[4:55]

def NLS(x):
    """
    Next Level Size
    NLS >= 5
    """
    return x[59:63]

"""
    Get Root Page

    //Accessing 2nd double word of partition table (pate1)
    //Ref: Power ISA Manual v3.0B, Book-III, section 5.7.6.1
    //           PTCR Layout
    // ====================================================
    // -----------------------------------------------
    // | /// |     PATB                | /// | PATS  |
    // -----------------------------------------------
    // 0     4                       51 52 58 59    63
    // PATB[4:51] holds the base address of the Partition Table,
    // right shifted by 12 bits.
    // This is because the address of the Partition base is
    // 4k aligned. Hence, the lower 12bits, which are always
    // 0 are ommitted from the PTCR.
    //
    // Thus, The Partition Table Base is obtained by (PATB << 12)
    //
    // PATS represents the partition table size right-shifted by 12 bits.
    // The minimal size of the partition table is 4k.
    // Thus partition table size = (1 << PATS + 12).
    //
    //        Partition Table
    //  ====================================================
    //  0    PATE0            63  PATE1             127
    //  |----------------------|----------------------|
    //  |                      |                      |
    //  |----------------------|----------------------|
    //  |                      |                      |
    //  |----------------------|----------------------|
    //  |                      |                      | <-- effLPID
    //  |----------------------|----------------------|
    //           .
    //           .
    //           .
    //  |----------------------|----------------------|
    //  |                      |                      |
    //  |----------------------|----------------------|
    //
    // The effective LPID  forms the index into the Partition Table.
    //
    // Each entry in the partition table contains 2 double words, PATE0, PATE1,
    // corresponding to that partition.
    //
    // In case of Radix, The structure of PATE0 and PATE1 is as follows.
    //
    //     PATE0 Layout
    // -----------------------------------------------
    // |1|RTS1|/|     RPDB          | RTS2 |  RPDS   |
    // -----------------------------------------------
    //  0 1  2 3 4                55 56  58 59      63
    //
    // HR[0] : For Radix Page table, first bit should be 1.
    // RTS1[1:2] : Gives one fragment of the Radix treesize
    // RTS2[56:58] : Gives the second fragment of the Radix Tree size.
    // RTS = (RTS1 << 3 + RTS2) + 31.
    //
    // RPDB[4:55] = Root Page Directory Base.
    // RPDS = Logarithm of Root Page Directory Size right shifted by 3.
    //        Thus, Root page directory size = 1 << (RPDS + 3).
    //        Note: RPDS >= 5.
    //
    //   PATE1 Layout
    // -----------------------------------------------
    // |///|       PRTB             |  //  |  PRTS   |
    // -----------------------------------------------
    // 0  3 4                     51 52  58 59     63
    //
    // PRTB[4:51]   = Process Table Base. This is aligned to size.
    // PRTS[59: 63] = Process Table Size right shifted by 12.
    //                Minimal size of the process table is 4k.
    //                Process Table Size = (1 << PRTS + 12).
    //                Note: PRTS <= 24.
    //
    //                Computing the size aligned Process Table Base:
    //                   table_base = (PRTB  & ~((1 << PRTS) - 1)) << 12
    //                Thus, the lower 12+PRTS bits of table_base will
    //                be zero.


    //Ref: Power ISA Manual v3.0B, Book-III, section 5.7.6.2
    //
    //        Process Table
    // ==========================
    //  0    PRTE0            63  PRTE1             127
    //  |----------------------|----------------------|
    //  |                      |                      |
    //  |----------------------|----------------------|
    //  |                      |                      |
    //  |----------------------|----------------------|
    //  |                      |                      | <-- effPID
    //  |----------------------|----------------------|
    //           .
    //           .
    //           .
    //  |----------------------|----------------------|
    //  |                      |                      |
    //  |----------------------|----------------------|
    //
    // The effective Process id (PID) forms the index into the Process Table.
    //
    // Each entry in the partition table contains 2 double words, PRTE0, PRTE1,
    // corresponding to that process
    //
    // In case of Radix, The structure of PRTE0 and PRTE1 is as follows.
    //
    //     PRTE0 Layout
    // -----------------------------------------------
    // |/|RTS1|/|     RPDB          | RTS2 |  RPDS   |
    // -----------------------------------------------
    //  0 1  2 3 4                55 56  58 59      63
    //
    // RTS1[1:2] : Gives one fragment of the Radix treesize
    // RTS2[56:58] : Gives the second fragment of the Radix Tree size.
    // RTS = (RTS1 << 3 + RTS2) << 31,
    //        since minimal Radix Tree size is 4G.
    //
    // RPDB = Root Page Directory Base.
    // RPDS = Root Page Directory Size right shifted by 3.
    //        Thus, Root page directory size = RPDS << 3.
    //        Note: RPDS >= 5.
    //
    //   PRTE1 Layout
    // -----------------------------------------------
    // |                      ///                    |
    // -----------------------------------------------
    // 0                                            63
    // All bits are reserved.


"""

# see qemu/target/ppc/mmu-radix64.c for reference
class RADIX:
    def __init__(self, mem, caller):
        self.mem = mem
        self.caller = caller
        #TODO move to lookup
        self.dsisr = self.caller.spr["DSISR"]
        self.dar   = self.caller.spr["DAR"]
        self.pidr  = self.caller.spr["PIDR"]
        self.prtbl = self.caller.spr["PRTBL"]

        # cached page table stuff
        self.pgtbl0 = 0
        self.pt0_valid = False
        self.pgtbl3 = 0
        self.pt3_valid = False

    def __call__(self, addr, sz):
        val = self.ld(addr.value, sz, swap=False)
        print("RADIX memread", addr, sz, val)
        return SelectableInt(val, sz*8)

    def ld(self, address, width=8, swap=True, check_in_mem=False,
                 instr_fetch=False):
        print("RADIX: ld from addr 0x%x width %d" % (address, width))

        priv = 1 # XXX TODO: read MSR PR bit here priv = not ctrl.msr(MSR_PR);
        if instr_fetch:
            mode = 'EXECUTE'
        else:
            mode = 'LOAD'
        addr = SelectableInt(address, 64)
        (shift, mbits, pgbase) = self._decode_prte(addr)
        #shift = SelectableInt(0, 32)

        pte = self._walk_tree(addr, pgbase, mode, mbits, shift, priv)
        # use pte to caclculate phys address
        return self.mem.ld(address, width, swap, check_in_mem)

        # XXX set SPRs on error

    # TODO implement
    def st(self, address, v, width=8, swap=True):
        print("RADIX: st to addr 0x%x width %d data %x" % (address, width, v))

        priv = 1 # XXX TODO: read MSR PR bit here priv = not ctrl.msr(MSR_PR);
        mode = 'STORE'
        addr = SelectableInt(address, 64)
        (shift, mbits, pgbase) = self._decode_prte(addr)
        pte = self._walk_tree(addr, pgbase, mode, mbits, shift, priv)

        # use pte to caclculate phys address (addr)
        return self.mem.st(addr.value, v, width, swap)

        # XXX set SPRs on error

    def memassign(self, addr, sz, val):
        print("memassign", addr, sz, val)
        self.st(addr.value, val.value, sz, swap=False)

    def _next_level(self,r):
        return rpte_valid(r), rpte_leaf(r)
        ## DSISR_R_BADCONFIG
        ## read_entry
        ## DSISR_NOPTE
        ## Prepare for next iteration

    def _walk_tree(self, addr, pgbase, mode, mbits, shift, priv=1):
        """walk tree

        // vaddr                    64 Bit
        // vaddr |-----------------------------------------------------|
        //       | Unused    |  Used                                   |
        //       |-----------|-----------------------------------------|
        //       | 0000000   | usefulBits = X bits (typically 52)      |
        //       |-----------|-----------------------------------------|
        //       |           |<--Cursize---->|                         |
        //       |           |    Index      |                         |
        //       |           |    into Page  |                         |
        //       |           |    Directory  |                         |
        //       |-----------------------------------------------------|
        //                        |                       |
        //                        V                       |
        // PDE  |---------------------------|             |
        //      |V|L|//|  NLB       |///|NLS|             |
        //      |---------------------------|             |
        // PDE = Page Directory Entry                     |
        // [0] = V = Valid Bit                            |
        // [1] = L = Leaf bit. If 0, then                 |
        // [4:55] = NLB = Next Level Base                 |
        //                right shifted by 8              |
        // [59:63] = NLS = Next Level Size                |
        //            |    NLS >= 5                       |
        //            |                                   V
        //            |                     |--------------------------|
        //            |                     |   usfulBits = X-Cursize  |
        //            |                     |--------------------------|
        //            |---------------------><--NLS-->|                |
        //                                  | Index   |                |
        //                                  | into    |                |
        //                                  | PDE     |                |
        //                                  |--------------------------|
        //                                                    |
        // If the next PDE obtained by                        |
        // (NLB << 8 + 8 * index) is a                        |
        // nonleaf, then repeat the above.                    |
        //                                                    |
        // If the next PDE is a leaf,                         |
        // then Leaf PDE structure is as                      |
        // follows                                            |
        //                                                    |
        //                                                    |
        // Leaf PDE                                           |
        // |------------------------------|           |----------------|
        // |V|L|sw|//|RPN|sw|R|C|/|ATT|EAA|           | usefulBits     |
        // |------------------------------|           |----------------|
        // [0] = V = Valid Bit                                 |
        // [1] = L = Leaf Bit = 1 if leaf                      |
        //                      PDE                            |
        // [2] = Sw = Sw bit 0.                                |
        // [7:51] = RPN = Real Page Number,                    V
        //          real_page = RPN << 12 ------------->  Logical OR
        // [52:54] = Sw Bits 1:3                               |
        // [55] = R = Reference                                |
        // [56] = C = Change                                   V
        // [58:59] = Att =                                Physical Address
        //           0b00 = Normal Memory
        //           0b01 = SAO
        //           0b10 = Non Idenmpotent
        //           0b11 = Tolerant I/O
        // [60:63] = Encoded Access
        //           Authority
        //
        """
        # get sprs
        print("_walk_tree")
        pidr  = self.caller.spr["PIDR"]
        prtbl = self.caller.spr["PRTBL"]
        print(pidr)
        print(prtbl)
        p = addr[55:63]
        print("last 8 bits ----------")
        print

        # get address of root entry
        prtable_addr = self._get_prtable_addr(shift, prtbl, addr, pidr)
        print("prtable_addr",prtable_addr)

        # read root entry - imcomplete
        swap = False
        check_in_mem = False
        entry_width = 8
        value = self.mem.ld(prtable_addr.value, entry_width, swap, check_in_mem)
        data = SelectableInt(value, 64) # convert to SelectableInt
        print("value",value)

        test_input = [
            SelectableInt(0x8000000000000007, 64), #valid
            SelectableInt(0xc000000000000000, 64) #exit
        ]
        index = 0

        # walk tree starts on prtbl
        while True:
            print("nextlevel----------------------------")
            l = test_input[index]
            index += 1
            valid, leaf = self._next_level(l)
            print("    valid, leaf", valid, leaf)
            if leaf:
                ok = self._check_perms(data, priv, mode)
                # TODO: check permissions
            else:
                data = l # TODO put actual data here
                newlookup = self._new_lookup(data, mbits, shift)
                if newlookup == 'badtree':
                    return None
                shift, mask, pgbase = newlookup
                print ("   next level", shift, mask, pgbase)
            if not valid:
                return None # TODO: return error
            if leaf:
                return None # TODO return something

    def _new_lookup(self, data, mbits, shift):
        """
        mbits := unsigned('0' & data(4 downto 0));
        if mbits < 5 or mbits > 16 or mbits > r.shift then
            v.state := RADIX_FINISH;
            v.badtree := '1'; -- throw error
        else
            v.shift := v.shift - mbits;
            v.mask_size := mbits(4 downto 0);
            v.pgbase := data(55 downto 8) & x"00"; NLB?
            v.state := RADIX_LOOKUP; --> next level
        end if;
        """
        mbits = data[59:64]
        print("mbits=", mbits)
        if mbits < 5 or mbits > 16:
            print("badtree")
            return "badtree"
        shift = shift - mbits
        mask_size = mbits[1:5] # get 4 LSBs
        pgbase = selectconcat(data[8:56], SelectableInt(0, 8)) # shift up 8
        return shift, mask_size, pgbase

    def _decode_prte(self, data):
        """PRTE0 Layout
           -----------------------------------------------
           |/|RTS1|/|     RPDB          | RTS2 |  RPDS   |
           -----------------------------------------------
            0 1  2 3 4                55 56  58 59      63
        """
        # note that SelectableInt does big-endian!  so the indices
        # below *directly* match the spec, unlike microwatt which
        # has to turn them around (to LE)
        zero = SelectableInt(0, 1)
        rts = selectconcat(zero,
                           data[56:59],      # RTS2
                           data[1:3],        # RTS1
                           )
        masksize = data[59:64]               # RPDS
        mbits = selectconcat(zero, masksize)
        pgbase = selectconcat(data[8:56],  # part of RPDB
                             SelectableInt(0, 16),)

        return (rts, mbits, pgbase)

    def _segment_check(self, addr, mbits, shift):
        """checks segment valid
                    mbits := '0' & r.mask_size;
            v.shift := r.shift + (31 - 12) - mbits;
            nonzero := or(r.addr(61 downto 31) and not finalmask(30 downto 0));
            if r.addr(63) /= r.addr(62) or nonzero = '1' then
                v.state := RADIX_FINISH;
                v.segerror := '1';
            elsif mbits < 5 or mbits > 16 or mbits > (r.shift + (31 - 12)) then
                v.state := RADIX_FINISH;
                v.badtree := '1';
            else
                v.state := RADIX_LOOKUP;
        """
        # note that SelectableInt does big-endian!  so the indices
        # below *directly* match the spec, unlike microwatt which
        # has to turn them around (to LE)
        mask = genmask(shift, 44)
        nonzero = addr[1:32] & mask[13:44] # mask 31 LSBs (BE numbered 13:44)
        print ("RADIX _segment_check nonzero", bin(nonzero.value))
        print ("RADIX _segment_check addr[0-1]", addr[0].value, addr[1].value)
        if addr[0] != addr[1] or nonzero == 1:
            return "segerror"
        limit = shift + (31 - 12)
        if mbits < 5 or mbits > 16 or mbits > limit:
            return "badtree"
        new_shift = shift + (31 - 12) - mbits
        return new_shift

    def _check_perms(self, data, priv, mode):
        """check page permissions
        // Leaf PDE                                           |
        // |------------------------------|           |----------------|
        // |V|L|sw|//|RPN|sw|R|C|/|ATT|EAA|           | usefulBits     |
        // |------------------------------|           |----------------|
        // [0] = V = Valid Bit                                 |
        // [1] = L = Leaf Bit = 1 if leaf                      |
        //                      PDE                            |
        // [2] = Sw = Sw bit 0.                                |
        // [7:51] = RPN = Real Page Number,                    V
        //          real_page = RPN << 12 ------------->  Logical OR
        // [52:54] = Sw Bits 1:3                               |
        // [55] = R = Reference                                |
        // [56] = C = Change                                   V
        // [58:59] = Att =                                Physical Address
        //           0b00 = Normal Memory
        //           0b01 = SAO
        //           0b10 = Non Idenmpotent
        //           0b11 = Tolerant I/O
        // [60:63] = Encoded Access
        //           Authority
        //
                    -- test leaf bit
                        -- check permissions and RC bits
                        perm_ok := '0';
                        if r.priv = '1' or data(3) = '0' then
                            if r.iside = '0' then
                                perm_ok := data(1) or (data(2) and not r.store);
                            else
                                -- no IAMR, so no KUEP support for now
                                -- deny execute permission if cache inhibited
                                perm_ok := data(0) and not data(5);
                            end if;
                        end if;
                        rc_ok := data(8) and (data(7) or not r.store);
                        if perm_ok = '1' and rc_ok = '1' then
                            v.state := RADIX_LOAD_TLB;
                        else
                            v.state := RADIX_FINISH;
                            v.perm_err := not perm_ok;
                            -- permission error takes precedence over RC error
                            v.rc_error := perm_ok;
                        end if;
        """
        # decode mode into something that matches microwatt equivalent code
        instr_fetch, store = 0, 0
        if mode == 'STORE':
            store = 1
        if mode == 'EXECUTE':
            inst_fetch = 1

        # check permissions and RC bits
        perm_ok = 0
        if priv == 1 or data[60] == 0:
            if instr_fetch == 0:
                perm_ok = data[62] | (data[61] & (store == 0))
            # no IAMR, so no KUEP support for now
            # deny execute permission if cache inhibited
            perm_ok = data[63] & ~data[58]
        rc_ok = data[55] & (data[56] | (store == 0))
        if perm_ok == 1 and rc_ok == 1:
            return True

        return "perm_err" if perm_ok == 0 else "rc_err"

    def _get_prtable_addr(self, shift, prtbl, addr, pid):
        """
        if r.addr(63) = '1' then
            effpid := x"00000000";
        else
            effpid := r.pid;
        end if;
        x"00" & r.prtbl(55 downto 36) &
                ((r.prtbl(35 downto 12) and not finalmask(23 downto 0)) or
                (effpid(31 downto 8) and finalmask(23 downto 0))) &
                effpid(7 downto 0) & "0000";
        """
        print ("_get_prtable_addr_", shift, prtbl, addr, pid)
        finalmask = genmask(shift, 44)
        finalmask24 = finalmask[20:44]
        if addr[0].value == 1:
            effpid = SelectableInt(0, 32)
        else:
            effpid = pid #self.pid # TODO, check on this
        zero16 = SelectableInt(0, 16)
        zero4 = SelectableInt(0, 4)
        res = selectconcat(zero16,
                           prtbl[8:28],                        #
                           (prtbl[28:52] & ~finalmask24) |     #
                           (effpid[0:24] & finalmask24),       #
                           effpid[24:32],
                           zero4
                           )
        return res

    def _get_pgtable_addr(self, mask_size, pgbase, addrsh):
        """
        x"00" & r.pgbase(55 downto 19) &
        ((r.pgbase(18 downto 3) and not mask) or (addrsh and mask)) &
        "000";
        """
        mask16 = genmask(mask_size+5, 16)
        zero8 = SelectableInt(0, 8)
        zero3 = SelectableInt(0, 3)
        res = selectconcat(zero8,
                           pgbase[8:45],              #
                           (prtbl[45:61] & ~mask16) | #
                           (addrsh       & mask16),   #
                           zero3
                           )
        return res

    def _get_pte(self, shift, addr, pde):
        """
        x"00" &
        ((r.pde(55 downto 12) and not finalmask) or
         (r.addr(55 downto 12) and finalmask))
        & r.pde(11 downto 0);
        """
        finalmask = genmask(shift, 44)
        zero8 = SelectableInt(0, 8)
        res = selectconcat(zero8,
                           (pde[8:52]  & ~finalmask) | #
                           (addr[8:52] & finalmask),   #
                           pde[52:64],
                           )
        return res


# very quick test of maskgen function (TODO, move to util later)
if __name__ == '__main__':
    # set up dummy minimal ISACaller
    spr = {'DSISR': SelectableInt(0, 64),
           'DAR': SelectableInt(0, 64),
           'PIDR': SelectableInt(0, 64),
           'PRTBL': SelectableInt(0, 64)
    }
    class ISACaller: pass
    caller = ISACaller()
    caller.spr = spr

    shift = SelectableInt(5, 6)
    mask = genmask(shift, 43)
    print ("    mask", bin(mask.value))

    mem = Mem(row_bytes=8)
    mem = RADIX(mem, caller)
    # -----------------------------------------------
    # |/|RTS1|/|     RPDB          | RTS2 |  RPDS   |
    # -----------------------------------------------
    # |0|1  2|3|4                55|56  58|59     63|
    data = SelectableInt(0, 64)
    data[1:3] = 0b01
    data[56:59] = 0b11
    data[59:64] = 0b01101 # mask
    data[55] = 1
    (rts, mbits, pgbase) = mem._decode_prte(data)
    print ("    rts", bin(rts.value), rts.bits)
    print ("    mbits", bin(mbits.value), mbits.bits)
    print ("    pgbase", hex(pgbase.value), pgbase.bits)
    addr = SelectableInt(0x1000, 64)
    check = mem._segment_check(addr, mbits, shift)
    print ("    segment check", check)

    print("walking tree")
    # addr = unchanged
    # pgbase = None
    mode = None
    #mbits = None
    shift = rts
    result = mem._walk_tree(addr, pgbase, mode, mbits, shift)
    print(result)
