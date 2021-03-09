# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2020, 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl
"""core of the python-based POWER9 simulator

this is part of a cycle-accurate POWER9 simulator.  its primary purpose is
not speed, it is for both learning and educational purposes, as well as
a method of verifying the HDL.

related bugs:

* https://bugs.libre-soc.org/show_bug.cgi?id=424
"""

from copy import copy
from soc.decoder.selectable_int import (FieldSelectableInt, SelectableInt,
                                        selectconcat)

from soc.decoder.power_enums import SPR as DEC_SPR

from soc.decoder.helpers import exts, gtu, ltu, undefined
import math
import sys


def swap_order(x, nbytes):
    x = x.to_bytes(nbytes, byteorder='little')
    x = int.from_bytes(x, byteorder='big', signed=False)
    return x



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


