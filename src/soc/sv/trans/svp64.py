# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl

"""SVP64 OpenPOWER v3.0B assembly translator

This class takes raw svp64 assembly mnemonics (aliases excluded) and
creates an EXT001-encoded "svp64 prefix" followed by a v3.0B opcode.

It is very simple and straightforward, the only weirdness being the
extraction of the register information and conversion to v3.0B numbering.

Encoding format of svp64: https://libre-soc.org/openpower/sv/svp64/
Bugtracker: https://bugs.libre-soc.org/show_bug.cgi?id=578
"""

import os, sys
from collections import OrderedDict

from soc.decoder.pseudo.pagereader import ISA
from soc.decoder.power_enums import get_csv, find_wiki_dir


# identifies register by type
def is_CR_3bit(regname):
    return regname in ['BF', 'BFA']

def is_CR_5bit(regname):
    return regname in ['BA', 'BB', 'BC', 'BI', 'BT']

def is_GPR(regname):
    return regname in ['RA', 'RB', 'RC', 'RS', 'RT']

def get_regtype(regname):
    if is_CR_3bit(regname):
        return "CR_3bit"
    if is_CR_5bit(regname):
        return "CR_5bit"
    if is_GPR(regname):
        return "GPR"


# gets SVP64 ReMap information
class SVP64RM:
    def __init__(self):
        self.instrs = {}
        pth = find_wiki_dir()
        for fname in os.listdir(pth):
            if fname.startswith("RM"):
                for entry in get_csv(fname):
                    self.instrs[entry['insn']] = entry


# decodes svp64 assembly listings and creates EXT001 svp64 prefixes
class SVP64:
    def __init__(self, lst):
        self.lst = lst
        self.trans = self.translate(lst)

    def __iter__(self):
        for insn in self.trans:
            yield insn

    def translate(self, lst):
        isa = ISA() # reads the v3.0B pseudo-code markdown files
        svp64 = SVP64RM() # reads the svp64 Remap entries for registers
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
            if v30b_op not in svp64.instrs:
                raise Exception("opcode %s of '%s' not an svp64 instruction" % \
                                (v30b_op, insn))
            isa.instr[v30b_op].regs[0]
            v30b_regs = isa.instr[v30b_op].regs[0]
            rm = svp64.instrs[v30b_op]
            print ("v3.0B regs", opcode, v30b_regs)
            print (rm)

            # right.  the first thing to do is identify the ordering of
            # the registers, by name.  the EXTRA2/3 ordering is in
            # rm['0']..rm['3'] but those fields contain the names RA, BB
            # etc.  we have to read the pseudocode to understand which
            # reg is which in our instruction. sigh.

            # first turn the svp64 rm into a "by name" dict, recording
            # which position in the RM EXTRA it goes into
            svp64_reg_byname = {}
            for i in range(4):
                rfield = rm[str(i)]
                if not rfield or rfield == '0':
                    continue
                print ("EXTRA field", i, rfield)
                rfield = rfield.split(";") # s:RA;d:CR1 etc.
                for r in rfield:
                    r = r[2:] # ignore s: and d:
                    svp64_reg_byname[r] = i # this reg in EXTRA position 0-3
            print ("EXTRA field index, by regname", svp64_reg_byname)

            # okaaay now we identify the field value (opcode N,N,N) with
            # the pseudo-code info (opcode RT, RA, RB)
            opregfields = zip(fields, v30b_regs) # err that was easy

            # now for each of those find its place in the EXTRA encoding
            extras = OrderedDict()
            for idx, (field, regname) in enumerate(opregfields):
                extra = svp64_reg_byname.get(regname, None)
                regtype = get_regtype(regname)
                extras[extra] = (idx, field, regname, regtype)
                print ("    ", extra, extras[extra])

            # great! got the extra fields in their associated positions:
            # also we know the register type. now to create the EXTRA encodings
            etype = rm['Etype'] # Extra type: EXTRA3/EXTRA2
            extra_bits = 0
            v30b_newfields = []
            for extra_idx, (idx, field, regname, regtype) in extras.items():
                # is it a field we don't alter/examine?  if so just put it
                # into newfields
                if regtype is None:
                    v30b_newfields.append(field)

                # first, decode the field number. "5.v" or "3.s" or "9"
                field = field.split(".")
                regmode = 'scalar' # default
                if len(field) == 2:
                    if field[1] == 's':
                        regmode = 'scalar'
                    elif field[1] == 'v':
                        regmode = 'vector'
                field = int(field[0]) # actual register number
                print ("    ", regmode, field)
                if regtype == 'GPR':
                    if regmode == 'scalar':
                        # cut into 2-bits 5-bits SS FFFFF
                        sv_extra = field >> 5
                        field = field & 0b11111
                    else:
                        # cut into 5-bits 2-bits FFFFF SS
                        sv_extra = field & 0b11
                        field = field >> 2
                    # now sanity-check. EXTRA3 is ok, EXTRA2 has limits
                    if etype == 'EXTRA2':
                        if regmode == 'scalar':
                            assert sv_extra & 0b10 == 0, \
                                "scalar field %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                        else:
                            assert sv_extra & 0b01 == 0, \
                                "vector field %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))

                # append altered field value to v3.0b
                v30b_newfields.append(str(field))

            print ("new v3.0B fields", v30b_op, v30b_newfields)
            print ()

        return res

if __name__ == '__main__':
    isa = SVP64(['slw 3, 1, 4',
                 'extsw 5, 3',
                 'sv.extsw 5, 3',
                 'sv.cmpi 5, 1, 3, 2',
                 'sv.setb 5, 3',
                 'sv.isel 64.v, 3, 2, 0'
                ])
    csvs = SVP64RM()
