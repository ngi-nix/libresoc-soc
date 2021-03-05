# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2020, 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2020 Michael Nolan
# Funded by NLnet http://nlnet.nl
"""core of the python-based POWER9 simulator

this is part of a cycle-accurate POWER9 simulator.  its primary purpose is
not speed, it is for both learning and educational purposes, as well as
a method of verifying the HDL.

related bugs:

* https://bugs.libre-soc.org/show_bug.cgi?id=424
"""

from nmigen.back.pysim import Settle
from functools import wraps
from copy import copy
from soc.decoder.orderedset import OrderedSet
from soc.decoder.selectable_int import (FieldSelectableInt, SelectableInt,
                                        selectconcat)
from soc.decoder.power_enums import (spr_dict, spr_byname, XER_bits,
                                     insns, MicrOp, In1Sel, In2Sel, In3Sel,
                                     OutSel, CROutSel)
from soc.decoder.helpers import exts, gtu, ltu, undefined
from soc.consts import PIb, MSRb  # big-endian (PowerISA versions)
from soc.decoder.power_svp64 import SVP64RM, decode_extra

from collections import namedtuple
import math
import sys

instruction_info = namedtuple('instruction_info',
                              'func read_regs uninit_regs write_regs ' +
                              'special_regs op_fields form asmregs')

special_sprs = {
    'LR': 8,
    'CTR': 9,
    'TAR': 815,
    'XER': 1,
    'VRSAVE': 256}


def swap_order(x, nbytes):
    x = x.to_bytes(nbytes, byteorder='little')
    x = int.from_bytes(x, byteorder='big', signed=False)
    return x


REG_SORT_ORDER = {
    # TODO (lkcl): adjust other registers that should be in a particular order
    # probably CA, CA32, and CR
    "RT": 0,
    "RA": 0,
    "RB": 0,
    "RS": 0,
    "CR": 0,
    "LR": 0,
    "CTR": 0,
    "TAR": 0,
    "CA": 0,
    "CA32": 0,
    "MSR": 0,

    "overflow": 1,
}


def create_args(reglist, extra=None):
    retval = list(OrderedSet(reglist))
    retval.sort(key=lambda reg: REG_SORT_ORDER[reg])
    if extra is not None:
        return [extra] + retval
    return retval


# very quick, TODO move to SelectableInt utils later
def genmask(shift, size):
    res = SelectableInt(0, size)
    for i in range(size):
        if i < shift:
            res[size-1-i] = SelectableInt(1, 1)
    return res

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

        # cached page table stuff
        self.pgtbl0 = 0
        self.pt0_valid = False
        self.pgtbl3 = 0
        self.pt3_valid = False

    def ld(self, address, width=8, swap=True, check_in_mem=False):
        print("RADIX: ld from addr 0x%x width %d" % (address, width))

        pte = self._walk_tree()
        # use pte to caclculate phys address
        return self.mem.ld(address, width, swap, check_in_mem)

    # TODO implement
    def st(self, addr, v, width=8, swap=True):
        print("RADIX: st to addr 0x%x width %d data %x" % (addr, width, v))
        # use pte to caclculate phys address (addr)
        return self.mem.st(addr, v, width, swap)

    # def memassign(self, addr, sz, val):
    def _next_level(self):
        return True
        ## DSISR_R_BADCONFIG
        ## read_entry
        ## DSISR_NOPTE
        ## Prepare for next iteration

    def _walk_tree(self):
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
        # walk tree starts on prtbl
        while True:
            ret = self._next_level()
            if ret: return ret

    def _decode_prte(self, data):
        """PRTE0 Layout
           -----------------------------------------------
           |/|RTS1|/|     RPDB          | RTS2 |  RPDS   |
           -----------------------------------------------
            0 1  2 3 4                55 56  58 59      63
        """
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
        mask = genmask(shift, 43)
        nonzero = addr[1:32] & mask[12:43]
        print ("RADIX _segment_check nonzero", bin(nonzero.value))
        print ("RADIX _segment_check addr[0-1]", addr[0].value, addr[1].value)
        if addr[0] != addr[1] or nonzero == 1:
            return "segerror"
        limit = shift + (31 - 12)
        if mbits < 5 or mbits > 16 or mbits > limit:
            return "badtree"
        new_shift = shift + (31 - 12) - mbits
        return new_shift

    def _check_perms(self):
        """check page permissions
                    -- test leaf bit
                    if data(62) = '1' then
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


class Mem:

    def __init__(self, row_bytes=8, initial_mem=None):
        self.mem = {}
        self.bytes_per_word = row_bytes
        self.word_log2 = math.ceil(math.log2(row_bytes))
        print("Sim-Mem", initial_mem, self.bytes_per_word, self.word_log2)
        if not initial_mem:
            return

        # different types of memory data structures recognised (for convenience)
        if isinstance(initial_mem, list):
            initial_mem = (0, initial_mem)
        if isinstance(initial_mem, tuple):
            startaddr, mem = initial_mem
            initial_mem = {}
            for i, val in enumerate(mem):
                initial_mem[startaddr + row_bytes*i] = (val, row_bytes)

        for addr, (val, width) in initial_mem.items():
            #val = swap_order(val, width)
            self.st(addr, val, width, swap=False)

    def _get_shifter_mask(self, wid, remainder):
        shifter = ((self.bytes_per_word - wid) - remainder) * \
            8  # bits per byte
        # XXX https://bugs.libre-soc.org/show_bug.cgi?id=377
        # BE/LE mode?
        shifter = remainder * 8
        mask = (1 << (wid * 8)) - 1
        print("width,rem,shift,mask", wid, remainder, hex(shifter), hex(mask))
        return shifter, mask

    # TODO: Implement ld/st of lesser width
    def ld(self, address, width=8, swap=True, check_in_mem=False):
        print("ld from addr 0x{:x} width {:d}".format(address, width))
        remainder = address & (self.bytes_per_word - 1)
        address = address >> self.word_log2
        assert remainder & (width - 1) == 0, "Unaligned access unsupported!"
        if address in self.mem:
            val = self.mem[address]
        elif check_in_mem:
            return None
        else:
            val = 0
        print("mem @ 0x{:x} rem {:d} : 0x{:x}".format(address, remainder, val))

        if width != self.bytes_per_word:
            shifter, mask = self._get_shifter_mask(width, remainder)
            print("masking", hex(val), hex(mask << shifter), shifter)
            val = val & (mask << shifter)
            val >>= shifter
        if swap:
            val = swap_order(val, width)
        print("Read 0x{:x} from addr 0x{:x}".format(val, address))
        return val

    def st(self, addr, v, width=8, swap=True):
        staddr = addr
        remainder = addr & (self.bytes_per_word - 1)
        addr = addr >> self.word_log2
        print("Writing 0x{:x} to ST 0x{:x} "
              "memaddr 0x{:x}/{:x}".format(v, staddr, addr, remainder, swap))
        assert remainder & (width - 1) == 0, "Unaligned access unsupported!"
        if swap:
            v = swap_order(v, width)
        if width != self.bytes_per_word:
            if addr in self.mem:
                val = self.mem[addr]
            else:
                val = 0
            shifter, mask = self._get_shifter_mask(width, remainder)
            val &= ~(mask << shifter)
            val |= v << shifter
            self.mem[addr] = val
        else:
            self.mem[addr] = v
        print("mem @ 0x{:x}: 0x{:x}".format(addr, self.mem[addr]))

    def __call__(self, addr, sz):
        val = self.ld(addr.value, sz, swap=False)
        print("memread", addr, sz, val)
        return SelectableInt(val, sz*8)

    def memassign(self, addr, sz, val):
        print("memassign", addr, sz, val)
        self.st(addr.value, val.value, sz, swap=False)


class GPR(dict):
    def __init__(self, decoder, isacaller, svstate, regfile):
        dict.__init__(self)
        self.sd = decoder
        self.isacaller = isacaller
        self.svstate = svstate
        for i in range(32):
            self[i] = SelectableInt(regfile[i], 64)

    def __call__(self, ridx):
        return self[ridx]

    def set_form(self, form):
        self.form = form

    def getz(self, rnum):
        # rnum = rnum.value # only SelectableInt allowed
        print("GPR getzero", rnum)
        if rnum == 0:
            return SelectableInt(0, 64)
        return self[rnum]

    def _get_regnum(self, attr):
        getform = self.sd.sigforms[self.form]
        rnum = getattr(getform, attr)
        return rnum

    def ___getitem__(self, attr):
        """ XXX currently not used
        """
        rnum = self._get_regnum(attr)
        offs = self.svstate.srcstep
        print("GPR getitem", attr, rnum, "srcoffs", offs)
        return self.regfile[rnum]

    def dump(self):
        for i in range(0, len(self), 8):
            s = []
            for j in range(8):
                s.append("%08x" % self[i+j].value)
            s = ' '.join(s)
            print("reg", "%2d" % i, s)


class PC:
    def __init__(self, pc_init=0):
        self.CIA = SelectableInt(pc_init, 64)
        self.NIA = self.CIA + SelectableInt(4, 64) # only true for v3.0B!

    def update_nia(self, is_svp64):
        increment = 8 if is_svp64 else 4
        self.NIA = self.CIA + SelectableInt(increment, 64)

    def update(self, namespace, is_svp64):
        """updates the program counter (PC) by 4 if v3.0B mode or 8 if SVP64
        """
        self.CIA = namespace['NIA'].narrow(64)
        self.update_nia(is_svp64)
        namespace['CIA'] = self.CIA
        namespace['NIA'] = self.NIA


# Simple-V: see https://libre-soc.org/openpower/sv
class SVP64State:
    def __init__(self, init=0):
        self.spr = SelectableInt(init, 32)
        # fields of SVSTATE, see https://libre-soc.org/openpower/sv/sprs/
        self.maxvl = FieldSelectableInt(self.spr, tuple(range(0,7)))
        self.vl = FieldSelectableInt(self.spr, tuple(range(7,14)))
        self.srcstep = FieldSelectableInt(self.spr, tuple(range(14,21)))
        self.dststep = FieldSelectableInt(self.spr, tuple(range(21,28)))
        self.subvl = FieldSelectableInt(self.spr, tuple(range(28,30)))
        self.svstep = FieldSelectableInt(self.spr, tuple(range(30,32)))


# SVP64 ReMap field
class SVP64RMFields:
    def __init__(self, init=0):
        self.spr = SelectableInt(init, 24)
        # SVP64 RM fields: see https://libre-soc.org/openpower/sv/svp64/
        self.mmode = FieldSelectableInt(self.spr, [0])
        self.mask = FieldSelectableInt(self.spr, tuple(range(1,4)))
        self.elwidth = FieldSelectableInt(self.spr, tuple(range(4,6)))
        self.ewsrc = FieldSelectableInt(self.spr, tuple(range(6,8)))
        self.subvl = FieldSelectableInt(self.spr, tuple(range(8,10)))
        self.extra = FieldSelectableInt(self.spr, tuple(range(10,19)))
        self.mode = FieldSelectableInt(self.spr, tuple(range(19,24)))
        # these cover the same extra field, split into parts as EXTRA2
        self.extra2 = list(range(4))
        self.extra2[0] = FieldSelectableInt(self.spr, tuple(range(10,12)))
        self.extra2[1] = FieldSelectableInt(self.spr, tuple(range(12,14)))
        self.extra2[2] = FieldSelectableInt(self.spr, tuple(range(14,16)))
        self.extra2[3] = FieldSelectableInt(self.spr, tuple(range(16,18)))
        self.smask = FieldSelectableInt(self.spr, tuple(range(16,19)))
        # and here as well, but EXTRA3
        self.extra3 = list(range(3))
        self.extra3[0] = FieldSelectableInt(self.spr, tuple(range(10,13)))
        self.extra3[1] = FieldSelectableInt(self.spr, tuple(range(13,16)))
        self.extra3[2] = FieldSelectableInt(self.spr, tuple(range(16,19)))


SVP64RM_MMODE_SIZE = len(SVP64RMFields().mmode.br)
SVP64RM_MASK_SIZE = len(SVP64RMFields().mask.br)
SVP64RM_ELWIDTH_SIZE = len(SVP64RMFields().elwidth.br)
SVP64RM_EWSRC_SIZE = len(SVP64RMFields().ewsrc.br)
SVP64RM_SUBVL_SIZE = len(SVP64RMFields().subvl.br)
SVP64RM_EXTRA2_SPEC_SIZE = len(SVP64RMFields().extra2[0].br)
SVP64RM_EXTRA3_SPEC_SIZE = len(SVP64RMFields().extra3[0].br)
SVP64RM_SMASK_SIZE = len(SVP64RMFields().smask.br)
SVP64RM_MODE_SIZE = len(SVP64RMFields().mode.br)


# SVP64 Prefix fields: see https://libre-soc.org/openpower/sv/svp64/
class SVP64PrefixFields:
    def __init__(self):
        self.insn = SelectableInt(0, 32)
        # 6 bit major opcode EXT001, 2 bits "identifying" (7, 9), 24 SV ReMap
        self.major = FieldSelectableInt(self.insn, tuple(range(0,6)))
        self.pid = FieldSelectableInt(self.insn, (7, 9)) # must be 0b11
        rmfields = [6, 8] + list(range(10,32)) # SVP64 24-bit RM (ReMap)
        self.rm = FieldSelectableInt(self.insn, rmfields)


SV64P_MAJOR_SIZE = len(SVP64PrefixFields().major.br)
SV64P_PID_SIZE = len(SVP64PrefixFields().pid.br)
SV64P_RM_SIZE = len(SVP64PrefixFields().rm.br)


class SPR(dict):
    def __init__(self, dec2, initial_sprs={}):
        self.sd = dec2
        dict.__init__(self)
        for key, v in initial_sprs.items():
            if isinstance(key, SelectableInt):
                key = key.value
            key = special_sprs.get(key, key)
            if isinstance(key, int):
                info = spr_dict[key]
            else:
                info = spr_byname[key]
            if not isinstance(v, SelectableInt):
                v = SelectableInt(v, info.length)
            self[key] = v

    def __getitem__(self, key):
        print("get spr", key)
        print("dict", self.items())
        # if key in special_sprs get the special spr, otherwise return key
        if isinstance(key, SelectableInt):
            key = key.value
        if isinstance(key, int):
            key = spr_dict[key].SPR
        key = special_sprs.get(key, key)
        if key == 'HSRR0':  # HACK!
            key = 'SRR0'
        if key == 'HSRR1':  # HACK!
            key = 'SRR1'
        if key in self:
            res = dict.__getitem__(self, key)
        else:
            if isinstance(key, int):
                info = spr_dict[key]
            else:
                info = spr_byname[key]
            dict.__setitem__(self, key, SelectableInt(0, info.length))
            res = dict.__getitem__(self, key)
        print("spr returning", key, res)
        return res

    def __setitem__(self, key, value):
        if isinstance(key, SelectableInt):
            key = key.value
        if isinstance(key, int):
            key = spr_dict[key].SPR
            print("spr key", key)
        key = special_sprs.get(key, key)
        if key == 'HSRR0':  # HACK!
            self.__setitem__('SRR0', value)
        if key == 'HSRR1':  # HACK!
            self.__setitem__('SRR1', value)
        print("setting spr", key, value)
        dict.__setitem__(self, key, value)

    def __call__(self, ridx):
        return self[ridx]

def get_pdecode_idx_in(dec2, name):
    op = dec2.dec.op
    in1_sel = yield op.in1_sel
    in2_sel = yield op.in2_sel
    in3_sel = yield op.in3_sel
    # get the IN1/2/3 from the decoder (includes SVP64 remap and isvec)
    in1 = yield dec2.e.read_reg1.data
    in2 = yield dec2.e.read_reg2.data
    in3 = yield dec2.e.read_reg3.data
    in1_isvec = yield dec2.in1_isvec
    in2_isvec = yield dec2.in2_isvec
    in3_isvec = yield dec2.in3_isvec
    print ("get_pdecode_idx", in1_sel, In1Sel.RA.value, in1, in1_isvec)
    # identify which regnames map to in1/2/3
    if name == 'RA':
        if (in1_sel == In1Sel.RA.value or
            (in1_sel == In1Sel.RA_OR_ZERO.value and in1 != 0)):
            return in1, in1_isvec
        if in1_sel == In1Sel.RA_OR_ZERO.value:
            return in1, in1_isvec
    elif name == 'RB':
        if in2_sel == In2Sel.RB.value:
            return in2, in2_isvec
        if in3_sel == In3Sel.RB.value:
            return in3, in3_isvec
    # XXX TODO, RC doesn't exist yet!
    elif name == 'RC':
        assert False, "RC does not exist yet"
    elif name == 'RS':
        if in1_sel == In1Sel.RS.value:
            return in1, in1_isvec
        if in2_sel == In2Sel.RS.value:
            return in2, in2_isvec
        if in3_sel == In3Sel.RS.value:
            return in3, in3_isvec
    return None, False


def get_pdecode_cr_out(dec2, name):
    op = dec2.dec.op
    out_sel = yield op.cr_out
    out_bitfield = yield dec2.dec_cr_out.cr_bitfield.data
    sv_cr_out = yield op.sv_cr_out
    spec = yield dec2.crout_svdec.spec
    sv_override = yield dec2.dec_cr_out.sv_override
    # get the IN1/2/3 from the decoder (includes SVP64 remap and isvec)
    out = yield dec2.e.write_cr.data
    o_isvec = yield dec2.o_isvec
    print ("get_pdecode_cr_out", out_sel, CROutSel.CR0.value, out, o_isvec)
    print ("    sv_cr_out", sv_cr_out)
    print ("    cr_bf", out_bitfield)
    print ("    spec", spec)
    print ("    override", sv_override)
    # identify which regnames map to out / o2
    if name == 'CR0':
        if out_sel == CROutSel.CR0.value:
            return out, o_isvec
    print ("get_pdecode_idx_out not found", name)
    return None, False


def get_pdecode_idx_out(dec2, name):
    op = dec2.dec.op
    out_sel = yield op.out_sel
    # get the IN1/2/3 from the decoder (includes SVP64 remap and isvec)
    out = yield dec2.e.write_reg.data
    o_isvec = yield dec2.o_isvec
    print ("get_pdecode_idx_out", out_sel, OutSel.RA.value, out, o_isvec)
    # identify which regnames map to out / o2
    if name == 'RA':
        if out_sel == OutSel.RA.value:
            return out, o_isvec
    elif name == 'RT':
        if out_sel == OutSel.RT.value:
            return out, o_isvec
    print ("get_pdecode_idx_out not found", name)
    return None, False


# XXX TODO
def get_pdecode_idx_out2(dec2, name):
    op = dec2.dec.op
    print ("TODO: get_pdecode_idx_out2", name)
    return None, False


class ISACaller:
    # decoder2 - an instance of power_decoder2
    # regfile - a list of initial values for the registers
    # initial_{etc} - initial values for SPRs, Condition Register, Mem, MSR
    # respect_pc - tracks the program counter.  requires initial_insns
    def __init__(self, decoder2, regfile, initial_sprs=None, initial_cr=0,
                 initial_mem=None, initial_msr=0,
                 initial_svstate=0,
                 initial_insns=None, respect_pc=False,
                 disassembly=None,
                 initial_pc=0,
                 bigendian=False,
                 mmu=False):

        self.bigendian = bigendian
        self.halted = False
        self.is_svp64_mode = False
        self.respect_pc = respect_pc
        if initial_sprs is None:
            initial_sprs = {}
        if initial_mem is None:
            initial_mem = {}
        if initial_insns is None:
            initial_insns = {}
            assert self.respect_pc == False, "instructions required to honor pc"

        print("ISACaller insns", respect_pc, initial_insns, disassembly)
        print("ISACaller initial_msr", initial_msr)

        # "fake program counter" mode (for unit testing)
        self.fake_pc = 0
        disasm_start = 0
        if not respect_pc:
            if isinstance(initial_mem, tuple):
                self.fake_pc = initial_mem[0]
                disasm_start = self.fake_pc
        else:
            disasm_start = initial_pc

        # disassembly: we need this for now (not given from the decoder)
        self.disassembly = {}
        if disassembly:
            for i, code in enumerate(disassembly):
                self.disassembly[i*4 + disasm_start] = code

        # set up registers, instruction memory, data memory, PC, SPRs, MSR
        self.svp64rm = SVP64RM()
        if isinstance(initial_svstate, int):
            initial_svstate = SVP64State(initial_svstate)
        self.svstate = initial_svstate
        self.gpr = GPR(decoder2, self, self.svstate, regfile)
        self.mem = Mem(row_bytes=8, initial_mem=initial_mem)
        if mmu:
            self.mem = RADIX(self.mem, self)
        self.imem = Mem(row_bytes=4, initial_mem=initial_insns)
        self.pc = PC()
        self.spr = SPR(decoder2, initial_sprs)
        self.msr = SelectableInt(initial_msr, 64)  # underlying reg

        # TODO, needed here:
        # FPR (same as GPR except for FP nums)
        # 4.2.2 p124 FPSCR (definitely "separate" - not in SPR)
        #            note that mffs, mcrfs, mtfsf "manage" this FPSCR
        # 2.3.1 CR (and sub-fields CR0..CR6 - CR0 SO comes from XER.SO)
        #         note that mfocrf, mfcr, mtcr, mtocrf, mcrxrx "manage" CRs
        #         -- Done
        # 2.3.2 LR   (actually SPR #8) -- Done
        # 2.3.3 CTR  (actually SPR #9) -- Done
        # 2.3.4 TAR  (actually SPR #815)
        # 3.2.2 p45 XER  (actually SPR #1) -- Done
        # 3.2.3 p46 p232 VRSAVE (actually SPR #256)

        # create CR then allow portions of it to be "selectable" (below)
        #rev_cr = int('{:016b}'.format(initial_cr)[::-1], 2)
        self.cr = SelectableInt(initial_cr, 64)  # underlying reg
        #self.cr = FieldSelectableInt(self._cr, list(range(32, 64)))

        # "undefined", just set to variable-bit-width int (use exts "max")
        #self.undefined = SelectableInt(0, 256)  # TODO, not hard-code 256!

        self.namespace = {}
        self.namespace.update(self.spr)
        self.namespace.update({'GPR': self.gpr,
                               'MEM': self.mem,
                               'SPR': self.spr,
                               'memassign': self.memassign,
                               'NIA': self.pc.NIA,
                               'CIA': self.pc.CIA,
                               'CR': self.cr,
                               'MSR': self.msr,
                               'undefined': undefined,
                               'mode_is_64bit': True,
                               'SO': XER_bits['SO']
                               })

        # update pc to requested start point
        self.set_pc(initial_pc)

        # field-selectable versions of Condition Register TODO check bitranges?
        self.crl = []
        for i in range(8):
            bits = tuple(range(i*4+32, (i+1)*4+32))  # errr... maybe?
            _cr = FieldSelectableInt(self.cr, bits)
            self.crl.append(_cr)
            self.namespace["CR%d" % i] = _cr

        self.decoder = decoder2.dec
        self.dec2 = decoder2

    def TRAP(self, trap_addr=0x700, trap_bit=PIb.TRAP):
        print("TRAP:", hex(trap_addr), hex(self.namespace['MSR'].value))
        # store CIA(+4?) in SRR0, set NIA to 0x700
        # store MSR in SRR1, set MSR to um errr something, have to check spec
        self.spr['SRR0'].value = self.pc.CIA.value
        self.spr['SRR1'].value = self.namespace['MSR'].value
        self.trap_nia = SelectableInt(trap_addr, 64)
        self.spr['SRR1'][trap_bit] = 1  # change *copy* of MSR in SRR1

        # set exception bits.  TODO: this should, based on the address
        # in figure 66 p1065 V3.0B and the table figure 65 p1063 set these
        # bits appropriately.  however it turns out that *for now* in all
        # cases (all trap_addrs) the exact same thing is needed.
        self.msr[MSRb.IR] = 0
        self.msr[MSRb.DR] = 0
        self.msr[MSRb.FE0] = 0
        self.msr[MSRb.FE1] = 0
        self.msr[MSRb.EE] = 0
        self.msr[MSRb.RI] = 0
        self.msr[MSRb.SF] = 1
        self.msr[MSRb.TM] = 0
        self.msr[MSRb.VEC] = 0
        self.msr[MSRb.VSX] = 0
        self.msr[MSRb.PR] = 0
        self.msr[MSRb.FP] = 0
        self.msr[MSRb.PMM] = 0
        self.msr[MSRb.TEs] = 0
        self.msr[MSRb.TEe] = 0
        self.msr[MSRb.UND] = 0
        self.msr[MSRb.LE] = 1

    def memassign(self, ea, sz, val):
        self.mem.memassign(ea, sz, val)

    def prep_namespace(self, formname, op_fields):
        # TODO: get field names from form in decoder*1* (not decoder2)
        # decoder2 is hand-created, and decoder1.sigform is auto-generated
        # from spec
        # then "yield" fields only from op_fields rather than hard-coded
        # list, here.
        fields = self.decoder.sigforms[formname]
        for name in op_fields:
            if name == 'spr':
                sig = getattr(fields, name.upper())
            else:
                sig = getattr(fields, name)
            val = yield sig
            # these are all opcode fields involved in index-selection of CR,
            # and need to do "standard" arithmetic.  CR[BA+32] for example
            # would, if using SelectableInt, only be 5-bit.
            if name in ['BF', 'BFA', 'BC', 'BA', 'BB', 'BT', 'BI']:
                self.namespace[name] = val
            else:
                self.namespace[name] = SelectableInt(val, sig.width)

        self.namespace['XER'] = self.spr['XER']
        self.namespace['CA'] = self.spr['XER'][XER_bits['CA']].value
        self.namespace['CA32'] = self.spr['XER'][XER_bits['CA32']].value

    def handle_carry_(self, inputs, outputs, already_done):
        inv_a = yield self.dec2.e.do.invert_in
        if inv_a:
            inputs[0] = ~inputs[0]

        imm_ok = yield self.dec2.e.do.imm_data.ok
        if imm_ok:
            imm = yield self.dec2.e.do.imm_data.data
            inputs.append(SelectableInt(imm, 64))
        assert len(outputs) >= 1
        print("outputs", repr(outputs))
        if isinstance(outputs, list) or isinstance(outputs, tuple):
            output = outputs[0]
        else:
            output = outputs
        gts = []
        for x in inputs:
            print("gt input", x, output)
            gt = (gtu(x, output))
            gts.append(gt)
        print(gts)
        cy = 1 if any(gts) else 0
        print("CA", cy, gts)
        if not (1 & already_done):
            self.spr['XER'][XER_bits['CA']] = cy

        print("inputs", already_done, inputs)
        # 32 bit carry
        # ARGH... different for OP_ADD... *sigh*...
        op = yield self.dec2.e.do.insn_type
        if op == MicrOp.OP_ADD.value:
            res32 = (output.value & (1 << 32)) != 0
            a32 = (inputs[0].value & (1 << 32)) != 0
            if len(inputs) >= 2:
                b32 = (inputs[1].value & (1 << 32)) != 0
            else:
                b32 = False
            cy32 = res32 ^ a32 ^ b32
            print("CA32 ADD", cy32)
        else:
            gts = []
            for x in inputs:
                print("input", x, output)
                print("     x[32:64]", x, x[32:64])
                print("     o[32:64]", output, output[32:64])
                gt = (gtu(x[32:64], output[32:64])) == SelectableInt(1, 1)
                gts.append(gt)
            cy32 = 1 if any(gts) else 0
            print("CA32", cy32, gts)
        if not (2 & already_done):
            self.spr['XER'][XER_bits['CA32']] = cy32

    def handle_overflow(self, inputs, outputs, div_overflow):
        if hasattr(self.dec2.e.do, "invert_in"):
            inv_a = yield self.dec2.e.do.invert_in
            if inv_a:
                inputs[0] = ~inputs[0]

        imm_ok = yield self.dec2.e.do.imm_data.ok
        if imm_ok:
            imm = yield self.dec2.e.do.imm_data.data
            inputs.append(SelectableInt(imm, 64))
        assert len(outputs) >= 1
        print("handle_overflow", inputs, outputs, div_overflow)
        if len(inputs) < 2 and div_overflow is None:
            return

        # div overflow is different: it's returned by the pseudo-code
        # because it's more complex than can be done by analysing the output
        if div_overflow is not None:
            ov, ov32 = div_overflow, div_overflow
        # arithmetic overflow can be done by analysing the input and output
        elif len(inputs) >= 2:
            output = outputs[0]

            # OV (64-bit)
            input_sgn = [exts(x.value, x.bits) < 0 for x in inputs]
            output_sgn = exts(output.value, output.bits) < 0
            ov = 1 if input_sgn[0] == input_sgn[1] and \
                output_sgn != input_sgn[0] else 0

            # OV (32-bit)
            input32_sgn = [exts(x.value, 32) < 0 for x in inputs]
            output32_sgn = exts(output.value, 32) < 0
            ov32 = 1 if input32_sgn[0] == input32_sgn[1] and \
                output32_sgn != input32_sgn[0] else 0

        self.spr['XER'][XER_bits['OV']] = ov
        self.spr['XER'][XER_bits['OV32']] = ov32
        so = self.spr['XER'][XER_bits['SO']]
        so = so | ov
        self.spr['XER'][XER_bits['SO']] = so

    def handle_comparison(self, outputs, cr_idx=0):
        out = outputs[0]
        assert isinstance(out, SelectableInt), \
            "out zero not a SelectableInt %s" % repr(outputs)
        print("handle_comparison", out.bits, hex(out.value))
        # TODO - XXX *processor* in 32-bit mode
        # https://bugs.libre-soc.org/show_bug.cgi?id=424
        # if is_32bit:
        #    o32 = exts(out.value, 32)
        #    print ("handle_comparison exts 32 bit", hex(o32))
        out = exts(out.value, out.bits)
        print("handle_comparison exts", hex(out))
        zero = SelectableInt(out == 0, 1)
        positive = SelectableInt(out > 0, 1)
        negative = SelectableInt(out < 0, 1)
        SO = self.spr['XER'][XER_bits['SO']]
        print("handle_comparison SO", SO)
        cr_field = selectconcat(negative, positive, zero, SO)
        self.crl[cr_idx].eq(cr_field)

    def set_pc(self, pc_val):
        self.namespace['NIA'] = SelectableInt(pc_val, 64)
        self.pc.update(self.namespace, self.is_svp64_mode)

    def setup_one(self):
        """set up one instruction
        """
        if self.respect_pc:
            pc = self.pc.CIA.value
        else:
            pc = self.fake_pc
        self._pc = pc
        ins = self.imem.ld(pc, 4, False, True)
        if ins is None:
            raise KeyError("no instruction at 0x%x" % pc)
        print("setup: 0x%x 0x%x %s" % (pc, ins & 0xffffffff, bin(ins)))
        print("CIA NIA", self.respect_pc, self.pc.CIA.value, self.pc.NIA.value)

        yield self.dec2.sv_rm.eq(0)
        yield self.dec2.dec.raw_opcode_in.eq(ins & 0xffffffff)
        yield self.dec2.dec.bigendian.eq(self.bigendian)
        yield self.dec2.state.msr.eq(self.msr.value)
        yield self.dec2.state.pc.eq(pc)
        yield self.dec2.state.svstate.eq(self.svstate.spr.value)

        # SVP64.  first, check if the opcode is EXT001, and SVP64 id bits set
        yield Settle()
        opcode = yield self.dec2.dec.opcode_in
        pfx = SVP64PrefixFields() # TODO should probably use SVP64PrefixDecoder
        pfx.insn.value = opcode
        major = pfx.major.asint(msb0=True) # MSB0 inversion
        print ("prefix test: opcode:", major, bin(major),
                pfx.insn[7] == 0b1, pfx.insn[9] == 0b1)
        self.is_svp64_mode = ((major == 0b000001) and
                              pfx.insn[7].value == 0b1 and
                              pfx.insn[9].value == 0b1)
        self.pc.update_nia(self.is_svp64_mode)
        if not self.is_svp64_mode:
            return

        # in SVP64 mode.  decode/print out svp64 prefix, get v3.0B instruction
        print ("svp64.rm", bin(pfx.rm.asint(msb0=True)))
        print ("    svstate.vl", self.svstate.vl.asint(msb0=True))
        print ("    svstate.mvl", self.svstate.maxvl.asint(msb0=True))
        sv_rm = pfx.rm.asint(msb0=True)
        ins = self.imem.ld(pc+4, 4, False, True)
        print("     svsetup: 0x%x 0x%x %s" % (pc+4, ins & 0xffffffff, bin(ins)))
        yield self.dec2.dec.raw_opcode_in.eq(ins & 0xffffffff) # v3.0B suffix
        yield self.dec2.sv_rm.eq(sv_rm)                        # svp64 prefix
        yield Settle()

    def execute_one(self):
        """execute one instruction
        """
        # get the disassembly code for this instruction
        if self.is_svp64_mode:
            code = self.disassembly[self._pc+4]
            print("    svp64 sim-execute", hex(self._pc), code)
        else:
            code = self.disassembly[self._pc]
            print("sim-execute", hex(self._pc), code)
        opname = code.split(' ')[0]
        yield from self.call(opname)

        # don't use this except in special circumstances
        if not self.respect_pc:
            self.fake_pc += 4

        print("execute one, CIA NIA", self.pc.CIA.value, self.pc.NIA.value)

    def get_assembly_name(self):
        # TODO, asmregs is from the spec, e.g. add RT,RA,RB
        # see http://bugs.libre-riscv.org/show_bug.cgi?id=282
        dec_insn = yield self.dec2.e.do.insn
        asmcode = yield self.dec2.dec.op.asmcode
        print("get assembly name asmcode", asmcode, hex(dec_insn))
        asmop = insns.get(asmcode, None)
        int_op = yield self.dec2.dec.op.internal_op

        # sigh reconstruct the assembly instruction name
        if hasattr(self.dec2.e.do, "oe"):
            ov_en = yield self.dec2.e.do.oe.oe
            ov_ok = yield self.dec2.e.do.oe.ok
        else:
            ov_en = False
            ov_ok = False
        if hasattr(self.dec2.e.do, "rc"):
            rc_en = yield self.dec2.e.do.rc.rc
            rc_ok = yield self.dec2.e.do.rc.ok
        else:
            rc_en = False
            rc_ok = False
        # grrrr have to special-case MUL op (see DecodeOE)
        print("ov %d en %d rc %d en %d op %d" %
              (ov_ok, ov_en, rc_ok, rc_en, int_op))
        if int_op in [MicrOp.OP_MUL_H64.value, MicrOp.OP_MUL_H32.value]:
            print("mul op")
            if rc_en & rc_ok:
                asmop += "."
        else:
            if not asmop.endswith("."):  # don't add "." to "andis."
                if rc_en & rc_ok:
                    asmop += "."
        if hasattr(self.dec2.e.do, "lk"):
            lk = yield self.dec2.e.do.lk
            if lk:
                asmop += "l"
        print("int_op", int_op)
        if int_op in [MicrOp.OP_B.value, MicrOp.OP_BC.value]:
            AA = yield self.dec2.dec.fields.FormI.AA[0:-1]
            print("AA", AA)
            if AA:
                asmop += "a"
        spr_msb = yield from self.get_spr_msb()
        if int_op == MicrOp.OP_MFCR.value:
            if spr_msb:
                asmop = 'mfocrf'
            else:
                asmop = 'mfcr'
        # XXX TODO: for whatever weird reason this doesn't work
        # https://bugs.libre-soc.org/show_bug.cgi?id=390
        if int_op == MicrOp.OP_MTCRF.value:
            if spr_msb:
                asmop = 'mtocrf'
            else:
                asmop = 'mtcrf'
        return asmop

    def get_spr_msb(self):
        dec_insn = yield self.dec2.e.do.insn
        return dec_insn & (1 << 20) != 0  # sigh - XFF.spr[-1]?

    def call(self, name):
        """call(opcode) - the primary execution point for instructions
        """
        name = name.strip()  # remove spaces if not already done so
        if self.halted:
            print("halted - not executing", name)
            return

        # TODO, asmregs is from the spec, e.g. add RT,RA,RB
        # see http://bugs.libre-riscv.org/show_bug.cgi?id=282
        asmop = yield from self.get_assembly_name()
        print("call", name, asmop)

        # check privileged
        int_op = yield self.dec2.dec.op.internal_op
        spr_msb = yield from self.get_spr_msb()

        instr_is_privileged = False
        if int_op in [MicrOp.OP_ATTN.value,
                      MicrOp.OP_MFMSR.value,
                      MicrOp.OP_MTMSR.value,
                      MicrOp.OP_MTMSRD.value,
                      # TODO: OP_TLBIE
                      MicrOp.OP_RFID.value]:
            instr_is_privileged = True
        if int_op in [MicrOp.OP_MFSPR.value,
                      MicrOp.OP_MTSPR.value] and spr_msb:
            instr_is_privileged = True

        print("is priv", instr_is_privileged, hex(self.msr.value),
              self.msr[MSRb.PR])
        # check MSR priv bit and whether op is privileged: if so, throw trap
        if instr_is_privileged and self.msr[MSRb.PR] == 1:
            self.TRAP(0x700, PIb.PRIV)
            self.namespace['NIA'] = self.trap_nia
            self.pc.update(self.namespace, self.is_svp64_mode)
            return

        # check halted condition
        if name == 'attn':
            self.halted = True
            return

        # check illegal instruction
        illegal = False
        if name not in ['mtcrf', 'mtocrf']:
            illegal = name != asmop

        if illegal:
            print("illegal", name, asmop)
            self.TRAP(0x700, PIb.ILLEG)
            self.namespace['NIA'] = self.trap_nia
            self.pc.update(self.namespace, self.is_svp64_mode)
            print("name %s != %s - calling ILLEGAL trap, PC: %x" %
                  (name, asmop, self.pc.CIA.value))
            return

        info = self.instrs[name]
        yield from self.prep_namespace(info.form, info.op_fields)

        # preserve order of register names
        input_names = create_args(list(info.read_regs) +
                                  list(info.uninit_regs))
        print(input_names)

        # get SVP64 entry for the current instruction
        sv_rm = self.svp64rm.instrs.get(name)
        if sv_rm is not None:
            dest_cr, src_cr, src_byname, dest_byname = decode_extra(sv_rm)
        else:
            dest_cr, src_cr, src_byname, dest_byname = False, False, {}, {}
        print ("sv rm", sv_rm, dest_cr, src_cr, src_byname, dest_byname)

        # get SVSTATE srcstep.  TODO: dststep (twin predication)
        srcstep = self.svstate.srcstep.asint(msb0=True)
        vl = self.svstate.vl.asint(msb0=True)
        mvl = self.svstate.maxvl.asint(msb0=True)

        # VL=0 in SVP64 mode means "do nothing: skip instruction"
        if self.is_svp64_mode and vl == 0:
            self.pc.update(self.namespace, self.is_svp64_mode)
            print("end of call", self.namespace['CIA'], self.namespace['NIA'])
            return

        # main input registers (RT, RA ...)
        inputs = []
        for name in input_names:
            # using PowerDecoder2, first, find the decoder index.
            # (mapping name RA RB RC RS to in1, in2, in3)
            regnum, is_vec = yield from get_pdecode_idx_in(self.dec2, name)
            if regnum is None:
                # doing this is not part of svp64, it's because output
                # registers, to be modified, need to be in the namespace.
                regnum, is_vec = yield from get_pdecode_idx_out(self.dec2, name)
            # here's where we go "vector".  TODO: zero-testing (RA_IS_ZERO)
            # XXX already done by PowerDecoder2, now
            #if is_vec:
            #   regnum += srcstep # TODO, elwidth overrides

            # in case getting the register number is needed, _RA, _RB
            regname = "_" + name
            self.namespace[regname] = regnum
            print('reading reg %s %d' % (name, regnum), is_vec)
            reg_val = self.gpr(regnum)
            inputs.append(reg_val)

        # "special" registers
        for special in info.special_regs:
            if special in special_sprs:
                inputs.append(self.spr[special])
            else:
                inputs.append(self.namespace[special])

        # clear trap (trap) NIA
        self.trap_nia = None

        print("inputs", inputs)
        results = info.func(self, *inputs)
        print("results", results)

        # "inject" decorator takes namespace from function locals: we need to
        # overwrite NIA being overwritten (sigh)
        if self.trap_nia is not None:
            self.namespace['NIA'] = self.trap_nia

        print("after func", self.namespace['CIA'], self.namespace['NIA'])

        # detect if CA/CA32 already in outputs (sra*, basically)
        already_done = 0
        if info.write_regs:
            output_names = create_args(info.write_regs)
            for name in output_names:
                if name == 'CA':
                    already_done |= 1
                if name == 'CA32':
                    already_done |= 2

        print("carry already done?", bin(already_done))
        if hasattr(self.dec2.e.do, "output_carry"):
            carry_en = yield self.dec2.e.do.output_carry
        else:
            carry_en = False
        if carry_en:
            yield from self.handle_carry_(inputs, results, already_done)

        # detect if overflow was in return result
        overflow = None
        if info.write_regs:
            for name, output in zip(output_names, results):
                if name == 'overflow':
                    overflow = output

        if hasattr(self.dec2.e.do, "oe"):
            ov_en = yield self.dec2.e.do.oe.oe
            ov_ok = yield self.dec2.e.do.oe.ok
        else:
            ov_en = False
            ov_ok = False
        print("internal overflow", overflow, ov_en, ov_ok)
        if ov_en & ov_ok:
            yield from self.handle_overflow(inputs, results, overflow)

        if hasattr(self.dec2.e.do, "rc"):
            rc_en = yield self.dec2.e.do.rc.rc
        else:
            rc_en = False
        if rc_en:
            regnum, is_vec = yield from get_pdecode_cr_out(self.dec2, "CR0")
            self.handle_comparison(results, regnum)

        # any modified return results?
        if info.write_regs:
            for name, output in zip(output_names, results):
                if name == 'overflow':  # ignore, done already (above)
                    continue
                if isinstance(output, int):
                    output = SelectableInt(output, 256)
                if name in ['CA', 'CA32']:
                    if carry_en:
                        print("writing %s to XER" % name, output)
                        self.spr['XER'][XER_bits[name]] = output.value
                    else:
                        print("NOT writing %s to XER" % name, output)
                elif name in info.special_regs:
                    print('writing special %s' % name, output, special_sprs)
                    if name in special_sprs:
                        self.spr[name] = output
                    else:
                        self.namespace[name].eq(output)
                    if name == 'MSR':
                        print('msr written', hex(self.msr.value))
                else:
                    regnum, is_vec = yield from get_pdecode_idx_out(self.dec2,
                                                name)
                    if regnum is None:
                        # temporary hack for not having 2nd output
                        regnum = yield getattr(self.decoder, name)
                        is_vec = False
                    print('writing reg %d %s' % (regnum, str(output)), is_vec)
                    if output.bits > 64:
                        output = SelectableInt(output.value, 64)
                    self.gpr[regnum] = output

        # check if it is the SVSTATE.src/dest step that needs incrementing
        # this is our Sub-Program-Counter loop from 0 to VL-1
        if self.is_svp64_mode:
            # XXX twin predication TODO
            vl = self.svstate.vl.asint(msb0=True)
            mvl = self.svstate.maxvl.asint(msb0=True)
            srcstep = self.svstate.srcstep.asint(msb0=True)
            print ("    svstate.vl", vl)
            print ("    svstate.mvl", mvl)
            print ("    svstate.srcstep", srcstep)
            # check if srcstep needs incrementing by one, stop PC advancing
            # svp64 loop can end early if the dest is scalar
            svp64_dest_vector = not (yield self.dec2.no_out_vec)
            if svp64_dest_vector and srcstep != vl-1:
                self.svstate.srcstep += SelectableInt(1, 7)
                self.pc.NIA.value = self.pc.CIA.value
                self.namespace['NIA'] = self.pc.NIA
                print("end of sub-pc call", self.namespace['CIA'],
                                     self.namespace['NIA'])
                return # DO NOT allow PC to update whilst Sub-PC loop running
            # reset to zero
            self.svstate.srcstep[0:7] = 0
            print ("    svstate.srcstep loop end (PC to update)")
            self.pc.update_nia(self.is_svp64_mode)
            self.namespace['NIA'] = self.pc.NIA

        # UPDATE program counter
        self.pc.update(self.namespace, self.is_svp64_mode)
        print("end of call", self.namespace['CIA'], self.namespace['NIA'])


def inject():
    """Decorator factory.

    this decorator will "inject" variables into the function's namespace,
    from the *dictionary* in self.namespace.  it therefore becomes possible
    to make it look like a whole stack of variables which would otherwise
    need "self." inserted in front of them (*and* for those variables to be
    added to the instance) "appear" in the function.

    "self.namespace['SI']" for example becomes accessible as just "SI" but
    *only* inside the function, when decorated.
    """
    def variable_injector(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            try:
                func_globals = func.__globals__  # Python 2.6+
            except AttributeError:
                func_globals = func.func_globals  # Earlier versions.

            context = args[0].namespace  # variables to be injected
            saved_values = func_globals.copy()  # Shallow copy of dict.
            func_globals.update(context)
            result = func(*args, **kwargs)
            print("globals after", func_globals['CIA'], func_globals['NIA'])
            print("args[0]", args[0].namespace['CIA'],
                  args[0].namespace['NIA'])
            args[0].namespace = func_globals
            #exec (func.__code__, func_globals)

            # finally:
            #    func_globals = saved_values  # Undo changes.

            return result

        return decorator

    return variable_injector


# very quick test of maskgen function (TODO, move to util later)
if __name__ == '__main__':
    shift = SelectableInt(5, 6)
    mask = genmask(shift, 43)
    print ("    mask", bin(mask.value))

    mem = Mem(row_bytes=8)
    mem = RADIX(mem, None)
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
