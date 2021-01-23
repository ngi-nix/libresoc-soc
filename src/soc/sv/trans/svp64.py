# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl

"""SVP64 OpenPOWER v3.0B assembly translator

This class takes raw svp64 assembly mnemonics (aliases excluded) and
creates an EXT001-encoded "svp64 prefix" followed by a v3.0B opcode.
It is very simple
"""

from soc.decoder.pseudo.pagereader import ISA


def is_CR_3bit(regname):
    return regname in ['BF', 'BFA']

def is_CR_5bit(regname):
    return regname in ['BA', 'BB', 'BC', 'BI', 'BT']

def is_GPR(regname):
    return regname in ['RA', 'RB', 'RC', 'RS', 'RT']


class SVP64:
    def __init__(self, lst):
        self.lst = lst
        self.trans = self.translate(lst)

    def __iter__(self):
        for insn in self.trans:
            yield insn

    def translate(self, lst):
        isa = ISA() # reads the v3.0B pseudo-code markdown files
        res = []
        for insn in lst:
            # find first space, to get opcode
            ls = insn.split(' ')
            opcode = ls[0]
            # now find opcode fields
            fields = ''.join(ls[1:]).split(',')
            fields = list(map(str.strip, fields))
            print (opcode, fields)

            # identify if is a svp64 mnemonic
            if not opcode.startswith('sv.'):
                res.append(insn) # unaltered
                continue

            # start working on decoding the svp64 op: sv.baseop.vec2.mode
            opmodes = opcode.split(".")[1:] # strip leading "sv."
            v30b_op = opmodes.pop(0)        # first is the v3.0B
            if v30b_op not in isa.instr:
                raise Exception("opcode %s of '%s' not supported" % \
                                (v30b_op, insn))

        return res

if __name__ == '__main__':
    isa = SVP64(['slw 3, 1, 4',
                 'extsw 5, 3'])

