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

#from nmigen.back.pysim import Settle
from copy import copy
from soc.decoder.selectable_int import (FieldSelectableInt, SelectableInt,
                                        selectconcat)
from soc.decoder.helpers import exts, gtu, ltu, undefined
from soc.decoder.isa.mem import Mem
from soc.consts import MSRb  # big-endian (PowerISA versions)

import math
import sys
import unittest

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

## Shift address bits 61--12 right by 0--47 bits and
## supply the least significant 16 bits of the result.
def addrshift(addr,shift):
    print("addrshift")
    print(addr)
    print(shift)
    x = addr.value >> shift.value
    return SelectableInt(x,16)

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

def RPDB(x):
    """
    Root Page Directory Base
    power isa docs says 4:55 investigate
    """
    return x[8:56]

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

testmem = {

           0x10000:    # PARTITION_TABLE_2 (not implemented yet)
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           0x800000000100000b,

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           0x8000000000040009,
           0x40000:     # RADIX_SECOND_LEVEL
                        # 	   V = 1 L = 1 SW = 0 RPN = 0
	                    # R = 1 C = 1 ATT = 0 EAA 0x7
           0xc000000000000187,

           0x1000000:   # PROCESS_TABLE_3
                       # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           0x40000000000300ad,
          }

# this one has a 2nd level RADIX with a RPN of 0x5000
testmem2 = {

           0x10000:    # PARTITION_TABLE_2 (not implemented yet)
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           0x800000000100000b,

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           0x8000000000040009,
           0x40000:     # RADIX_SECOND_LEVEL
                        # 	   V = 1 L = 1 SW = 0 RPN = 0x5000
	                    # R = 1 C = 1 ATT = 0 EAA 0x7
           0xc000000005000187,

           0x1000000:   # PROCESS_TABLE_3
                       # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           0x40000000000300ad,
          }

testresult = """
    prtbl = 1000000
    DCACHE GET 1000000 PROCESS_TABLE_3
    DCACHE GET 30000 RADIX_ROOT_PTE V = 1 L = 0
    DCACHE GET 40000 RADIX_SECOND_LEVEL V = 1 L = 1
    DCACHE GET 10000 PARTITION_TABLE_2
translated done 1 err 0 badtree 0 addr 40000 pte 0
"""

# see qemu/target/ppc/mmu-radix64.c for reference
class RADIX:
    def __init__(self, mem, caller):
        self.mem = mem
        self.caller = caller
        if caller is not None:
            print("caller")
            print(caller)
            self.dsisr = self.caller.spr["DSISR"]
            self.dar   = self.caller.spr["DAR"]
            self.pidr  = self.caller.spr["PIDR"]
            self.prtbl = self.caller.spr["PRTBL"]
            self.msr   = self.caller.msr

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

        priv = ~(self.msr[MSRb.PR].value) # problem-state ==> privileged
        if instr_fetch:
            mode = 'EXECUTE'
        else:
            mode = 'LOAD'
        addr = SelectableInt(address, 64)
        (shift, mbits, pgbase) = self._decode_prte(addr)
        #shift = SelectableInt(0, 32)

        pte = self._walk_tree(addr, pgbase, mode, mbits, shift, priv)

        # use pte to load from phys address
        return self.mem.ld(pte.value, width, swap, check_in_mem)

        # XXX set SPRs on error

    # TODO implement
    def st(self, address, v, width=8, swap=True):
        print("RADIX: st to addr 0x%x width %d data %x" % (address, width, v))

        priv = ~(self.msr[MSRb.PR].value) # problem-state ==> privileged
        mode = 'STORE'
        addr = SelectableInt(address, 64)
        (shift, mbits, pgbase) = self._decode_prte(addr)
        pte = self._walk_tree(addr, pgbase, mode, mbits, shift, priv)

        # use pte to store at phys address
        return self.mem.st(pte.value, v, width, swap)

        # XXX set SPRs on error

    def memassign(self, addr, sz, val):
        print("memassign", addr, sz, val)
        self.st(addr.value, val.value, sz, swap=False)

    def _next_level(self, addr, entry_width, swap, check_in_mem):
        # implement read access to mmu mem here

        # DO NOT perform byte-swapping: load 8 bytes (that's the entry size)
        value = self.mem.ld(addr.value, 8, False, check_in_mem)
        if value is None:
            return "address lookup %x not found" % addr.value
        # assert(value is not None, "address lookup %x not found" % addr.value)

        print("addr", hex(addr.value))
        data = SelectableInt(value, 64) # convert to SelectableInt
        print("value", hex(value))
        # index += 1
        return data;

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
        shift = selectconcat(SelectableInt(0,1), prtbl[58:63]) # TODO verify
        addr_next = self._get_prtable_addr(shift, prtbl, addr, pidr)
        print("starting with prtable, addr_next",addr_next)

        assert(addr_next.bits == 64)
        #only for first unit tests assert(addr_next.value == 0x1000000)

        # read an entry from prtable
        swap = False
        check_in_mem = False
        entry_width = 8
        data = self._next_level(addr_next, entry_width, swap, check_in_mem)
        print("pr_table",data)
        pgtbl = data # this is cached in microwatt (as v.pgtbl3 / v.pgtbl0)

        # rts = shift = unsigned('0' & data(62 downto 61) & data(7 downto 5));
        shift = selectconcat(SelectableInt(0,1), data[1:3], data[55:58])
        assert(shift.bits==6) # variable rts : unsigned(5 downto 0);
        print("shift",shift)

        # mbits := unsigned('0' & data(4 downto 0));
        mbits = selectconcat(SelectableInt(0,1), data[58:63])
        assert(mbits.bits==6) #variable mbits : unsigned(5 downto 0);

        # WIP
        if mbits==0:
            return "invalid"

        # mask_size := mbits(4 downto 0);
        mask_size = mbits[0:5];
        assert(mask_size.bits==5)
        print("before segment check ==========")
        print("mask_size:",bin(mask_size.value))
        print("mbits:",bin(mbits.value))

        print("calling segment_check")

        mbits = selectconcat(SelectableInt(0,1), mask_size)
        shift = self._segment_check(addr, mbits, shift)
        print("shift",shift)

        # v.pgbase := pgtbl(55 downto 8) & x"00";
        # see test_RPDB for reference
        zero8 = SelectableInt(0,8)

        pgbase = selectconcat(zero8,RPDB(pgtbl),zero8)
        print("pgbase",pgbase)
        #assert(pgbase.value==0x30000)

        addrsh = addrshift(addr,shift)
        print("addrsh",addrsh)

        addr_next = self._get_pgtable_addr(mask_size, pgbase, addrsh)
        print("DONE addr_next",addr_next)

        # walk tree
        while True:
            print("nextlevel----------------------------")
            # read an entry
            swap = False
            check_in_mem = False
            entry_width = 8

            data = self._next_level(addr_next, entry_width, swap, check_in_mem)
            valid = rpte_valid(data)
            leaf = rpte_leaf(data)

            print("    valid, leaf", valid, leaf)
            if not valid:
                return "invalid" # TODO: return error
            if leaf:
                print ("is leaf, checking perms")
                ok = self._check_perms(data, priv, mode)
                if ok == True: # data was ok, found phys address, return it?
                    paddr = self._get_pte(addrsh, addr, data)
                    print ("    phys addr", hex(paddr.value))
                    return paddr
                return ok # return the error code
            else:
                newlookup = self._new_lookup(data, shift)
                if newlookup == 'badtree':
                    return newlookup
                shift, mask, pgbase = newlookup
                print ("   next level", shift, mask, pgbase)
                shift = SelectableInt(shift.value,16) #THIS is wrong !!!
                print("calling _get_pgtable_addr")
                print(mask)    #SelectableInt(value=0x9, bits=4)
                print(pgbase)  #SelectableInt(value=0x40000, bits=56)
                print(shift)   #SelectableInt(value=0x4, bits=16) #FIXME
                pgbase = SelectableInt(pgbase.value, 64)
                addrsh = addrshift(addr,shift)
                addr_next = self._get_pgtable_addr(mask, pgbase, addrsh)
                print("addr_next",addr_next)
                print("addrsh",addrsh)

    def _new_lookup(self, data, shift):
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
        if mbits < 5 or mbits > 16: #fixme compare with r.shift
            print("badtree")
            return "badtree"
        # reduce shift (has to be done at same bitwidth)
        shift = shift - selectconcat(SelectableInt(0, 1), mbits)
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
        nonzero = addr[2:33] & mask[13:44] # mask 31 LSBs (BE numbered 13:44)
        print ("RADIX _segment_check nonzero", bin(nonzero.value))
        print ("RADIX _segment_check addr[0-1]", addr[0].value, addr[1].value)
        if addr[0] != addr[1] or nonzero != 0:
            return "segerror"
        limit = shift + (31 - 12)
        if mbits.value < 5 or mbits.value > 16 or mbits.value > limit.value:
            return "badtree mbits="+str(mbits.value)+" limit="+str(limit.value)
        new_shift = shift + (31 - 12) - mbits
        # TODO verify that returned result is correct
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
        print ("_get_prtable_addr", shift, prtbl, addr, pid)
        finalmask = genmask(shift, 44)
        finalmask24 = finalmask[20:44]
        if addr[0].value == 1:
            effpid = SelectableInt(0, 32)
        else:
            effpid = pid #self.pid # TODO, check on this
        zero8 = SelectableInt(0, 8)
        zero4 = SelectableInt(0, 4)
        res = selectconcat(zero8,
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
                           (pgbase[45:61] & ~mask16) | #
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
        shift.value = 12
        finalmask = genmask(shift, 44)
        zero8 = SelectableInt(0, 8)
        rpn = pde[8:52]       # RPN = Real Page Number
        abits = addr[8:52] # non-masked address bits
        print("     get_pte RPN", hex(rpn.value))
        print("             abits", hex(abits.value))
        print("             shift", shift.value)
        print("             finalmask", bin(finalmask.value))
        res = selectconcat(zero8,
                           (rpn  & ~finalmask) | #
                           (abits & finalmask),   #
                           addr[52:64],
                           )
        return res

class TestRadixMMU(unittest.TestCase):

    def test_genmask(self):
        shift = SelectableInt(5, 6)
        mask = genmask(shift, 43)
        print ("    mask", bin(mask.value))

        self.assertEqual(mask.value, 0b11111, "mask should be 5 1s")

    def test_RPDB(self):
        inp = SelectableInt(0x40000000000300ad, 64)

        rtdb = RPDB(inp)
        print("rtdb",rtdb,bin(rtdb.value))
        self.assertEqual(rtdb.value,0x300,"rtdb should be 0x300")

        result = selectconcat(rtdb,SelectableInt(0,8))
        print("result",result)


    def test_get_pgtable_addr(self):

        mem = None
        caller = None
        dut = RADIX(mem, caller)

        mask_size=4
        pgbase = SelectableInt(0,64)
        addrsh = SelectableInt(0,16)
        ret = dut._get_pgtable_addr(mask_size, pgbase, addrsh)
        print("ret=", ret)
        self.assertEqual(ret, 0, "pgtbl_addr should be 0")

    def test_walk_tree_1(self):

        # test address as in
        # https://github.com/power-gem5/gem5/blob/gem5-experimental/src/arch/power/radix_walk_example.txt#L65
        testaddr = 0x1000
        expected = 0x1000

        # starting prtbl
        prtbl = 0x1000000

        # set up dummy minimal ISACaller
        spr = {'DSISR': SelectableInt(0, 64),
               'DAR': SelectableInt(0, 64),
               'PIDR': SelectableInt(0, 64),
               'PRTBL': SelectableInt(prtbl, 64)
        }
        # set problem state == 0 (other unit tests, set to 1)
        msr = SelectableInt(0, 64)
        msr[MSRb.PR] = 0
        class ISACaller: pass
        caller = ISACaller()
        caller.spr = spr
        caller.msr = msr

        shift = SelectableInt(5, 6)
        mask = genmask(shift, 43)
        print ("    mask", bin(mask.value))

        mem = Mem(row_bytes=8, initial_mem=testmem)
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
        addr = SelectableInt(testaddr,64)
        # pgbase = None
        mode = None
        #mbits = None
        shift = rts
        result = mem._walk_tree(addr, pgbase, mode, mbits, shift)
        print("     walking tree result", result)
        print("should be", testresult)
        self.assertEqual(result.value, expected,
                             "expected 0x%x got 0x%x" % (expected,
                                                    result.value))


    def test_walk_tree_2(self):

        # test address slightly different
        testaddr = 0x1101
        expected = 0x5001101

        # starting prtbl
        prtbl = 0x1000000

        # set up dummy minimal ISACaller
        spr = {'DSISR': SelectableInt(0, 64),
               'DAR': SelectableInt(0, 64),
               'PIDR': SelectableInt(0, 64),
               'PRTBL': SelectableInt(prtbl, 64)
        }
        # set problem state == 0 (other unit tests, set to 1)
        msr = SelectableInt(0, 64)
        msr[MSRb.PR] = 0
        class ISACaller: pass
        caller = ISACaller()
        caller.spr = spr
        caller.msr = msr

        shift = SelectableInt(5, 6)
        mask = genmask(shift, 43)
        print ("    mask", bin(mask.value))

        mem = Mem(row_bytes=8, initial_mem=testmem2)
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
        addr = SelectableInt(testaddr,64)
        # pgbase = None
        mode = None
        #mbits = None
        shift = rts
        result = mem._walk_tree(addr, pgbase, mode, mbits, shift)
        print("     walking tree result", result)
        print("should be", testresult)
        self.assertEqual(result.value, expected,
                             "expected 0x%x got 0x%x" % (expected,
                                                    result.value))


if __name__ == '__main__':
    unittest.main()
