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

# decode GPR into sv extra
def  get_extra_gpr(etype, regmode, field):
    if regmode == 'scalar':
        # cut into 2-bits 5-bits SS FFFFF
        sv_extra = field >> 5
        field = field & 0b11111
    else:
        # cut into 5-bits 2-bits FFFFF SS
        sv_extra = field & 0b11
        field = field >> 2
    return sv_extra, field


# decode 3-bit CR into sv extra
def  get_extra_cr_3bit(etype, regmode, field):
    if regmode == 'scalar':
        # cut into 2-bits 3-bits SS FFF
        sv_extra = field >> 3
        field = field & 0b111
    else:
        # cut into 3-bits 4-bits FFF SSSS but will cut 2 zeros off later
        sv_extra = field & 0b1111
        field = field >> 4
    return sv_extra, field


# decodes SUBVL
def decode_subvl(encoding):
    pmap = {'2': 0b01, '3': 0b10, '4': 0b11}
    assert encoding in pmap, \
        "encoding %s for SUBVL not recognised" % encoding
    return pmap[encoding]


# decodes elwidth
def decode_elwidth(encoding):
    pmap = {'8': 0b11, '16': 0b10, '32': 0b01}
    assert encoding in pmap, \
        "encoding %s for elwidth not recognised" % encoding
    return pmap[encoding]


# decodes predicate register encoding
def decode_predicate(encoding):
    pmap = { # integer
            '1<<r3': (0, 0b001),
            'r3'   : (0, 0b010),
            '~r3'   : (0, 0b011),
            'r10'   : (0, 0b100),
            '~r10'  : (0, 0b101),
            'r30'   : (0, 0b110),
            '~r30'  : (0, 0b111),
            # CR
            'lt'    : (1, 0b000),
            'nl'    : (1, 0b001), 'ge'    : (1, 0b001), # same value
            'gt'    : (1, 0b010),
            'ng'    : (1, 0b011), 'le'    : (1, 0b011), # same value
            'eq'    : (1, 0b100),
            'ne'    : (1, 0b101),
            'so'    : (1, 0b110), 'un'    : (1, 0b110), # same value
            'ns'    : (1, 0b111), 'nu'    : (1, 0b111), # same value
           }
    assert encoding in pmap, \
        "encoding %s for predicate not recognised" % encoding
    return pmap[encoding]


# decodes "Mode" in similar way to BO field (supposed to, anyway)
def decode_bo(encoding):
    pmap = { # TODO: double-check that these are the same as Branch BO
            'lt'    : 0b000,
            'nl'    : 0b001, 'ge'    : 0b001, # same value
            'gt'    : 0b010,
            'ng'    : 0b011, 'le'    : 0b011, # same value
            'eq'    : 0b100,
            'ne'    : 0b101,
            'so'    : 0b110, 'un'    : 0b110, # same value
            'ns'    : 0b111, 'nu'    : 0b111, # same value
           }
    assert encoding in pmap, \
        "encoding %s for BO Mode not recognised" % encoding
    return pmap[encoding]

# partial-decode fail-first mode
def decode_ffirst(encoding):
    if encoding in ['RC1', '~RC1']:
        return encoding
    return decode_bo(encoding)


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
            print ("opcode, fields", ls, opcode, fields)

            # identify if is a svp64 mnemonic
            if not opcode.startswith('sv.'):
                res.append(insn) # unaltered
                continue
            opcode = opcode[3:] # strip leading "sv."

            # start working on decoding the svp64 op: sv.baseop/vec2.mode
            opcode = opcode.split("/") # split at "/"
            v30b_op = opcode[0]       # first is the v3.0B
            if len(opcode) == 1:
                opmodes = [] # no sv modes
            else:
                opmodes = opcode[1].split(".") # second splits by dots

            # check instruction ends with dot
            rc_mode = v30b_op.endswith('.')
            if rc_mode:
                v30b_op = v30b_op[:-1]

            if v30b_op not in isa.instr:
                raise Exception("opcode %s of '%s' not supported" % \
                                (v30b_op, insn))
            if v30b_op not in svp64.instrs:
                raise Exception("opcode %s of '%s' not an svp64 instruction" % \
                                (v30b_op, insn))
            isa.instr[v30b_op].regs[0]
            v30b_regs = isa.instr[v30b_op].regs[0]
            rm = svp64.instrs[v30b_op]
            print ("v3.0B op", v30b_op, "Rc=1" if rc_mode else '')
            print ("v3.0B regs", opcode, v30b_regs)
            print (rm)

            # right.  the first thing to do is identify the ordering of
            # the registers, by name.  the EXTRA2/3 ordering is in
            # rm['0']..rm['3'] but those fields contain the names RA, BB
            # etc.  we have to read the pseudocode to understand which
            # reg is which in our instruction. sigh.

            # first turn the svp64 rm into a "by name" dict, recording
            # which position in the RM EXTRA it goes into
            # also: record if the src or dest was a CR, for sanity-checking
            # (elwidth overrides on CRs are banned)
            dest_reg_cr, src_reg_cr = False, False
            svp64_reg_byname = {}
            for i in range(4):
                rfield = rm[str(i)]
                if not rfield or rfield == '0':
                    continue
                print ("EXTRA field", i, rfield)
                rfield = rfield.split(";") # s:RA;d:CR1 etc.
                for r in rfield:
                    rtype = r[0]
                    r = r[2:] # ignore s: and d:
                    svp64_reg_byname[r] = i # this reg in EXTRA position 0-3
                    # check the regtype (if CR, record that)
                    regtype = get_regtype(r)
                    if regtype in ['CR_3bit', 'CR_5bit']:
                        if rtype == 'd':
                            dest_reg_cr = True
                        if rtype == 'd':
                            src_reg_cr = True

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
            ptype = rm['Ptype'] # Predication type: Twin / Single
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
                print ("    ", regmode, field, end=" ")

                # XXX TODO: the following is a bit of a laborious repeated
                # mess, which could (and should) easily be parameterised.

                # encode SV-GPR field into extra, v3.0field
                if regtype == 'GPR':
                    sv_extra, field = get_extra_gpr(etype, regmode, field)
                    # now sanity-check. EXTRA3 is ok, EXTRA2 has limits
                    # (and shrink to a single bit if ok)
                    if etype == 'EXTRA2':
                        if regmode == 'scalar':
                            # range is r0-r63 in increments of 1
                            assert (sv_extra >> 1) == 0, \
                                "scalar GPR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as scalar
                            sv_extra = sv_extra & 0b01
                        else:
                            # range is r0-r127 in increments of 4
                            assert sv_extra & 0b01 == 0, \
                                "vector field %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as vector (bit 2 set)
                            sv_extra = 0b10 | (sv_extra >> 1)
                    elif regmode == 'vector':
                        # EXTRA3 vector bit needs marking
                        sv_extra |= 0b100

                # encode SV-CR 3-bit field into extra, v3.0field
                elif regtype == 'CR_3bit':
                    sv_extra, field = get_extra_cr_3bit(etype, regmode, field)
                    # now sanity-check (and shrink afterwards)
                    if etype == 'EXTRA2':
                        if regmode == 'scalar':
                            # range is CR0-CR15 in increments of 1
                            assert (sv_extra >> 1) == 0, \
                                "scalar CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as scalar
                            sv_extra = sv_extra & 0b01
                        else:
                            # range is CR0-CR127 in increments of 16
                            assert sv_extra & 0b111 == 0, \
                                "vector CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as vector (bit 2 set)
                            sv_extra = 0b10 | (sv_extra >> 3)
                    else:
                        if regmode == 'scalar':
                            # range is CR0-CR31 in increments of 1
                            assert (sv_extra >> 2) == 0, \
                                "scalar CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as scalar
                            sv_extra = sv_extra & 0b11
                        else:
                            # range is CR0-CR127 in increments of 8
                            assert sv_extra & 0b11 == 0, \
                                "vector CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as vector (bit 3 set)
                            sv_extra = 0b100 | (sv_extra >> 2)

                # encode SV-CR 5-bit field into extra, v3.0field
                # *sigh* this is the same as 3-bit except the 2 LSBs are
                # passed through
                elif regtype == 'CR_5bit':
                    cr_subfield = field & 0b11
                    field = field >> 2 # strip bottom 2 bits
                    sv_extra, field = get_extra_cr_3bit(etype, regmode, field)
                    # now sanity-check (and shrink afterwards)
                    if etype == 'EXTRA2':
                        if regmode == 'scalar':
                            # range is CR0-CR15 in increments of 1
                            assert (sv_extra >> 1) == 0, \
                                "scalar CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as scalar
                            sv_extra = sv_extra & 0b01
                        else:
                            # range is CR0-CR127 in increments of 16
                            assert sv_extra & 0b111 == 0, \
                                "vector CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as vector (bit 2 set)
                            sv_extra = 0b10 | (sv_extra >> 3)
                    else:
                        if regmode == 'scalar':
                            # range is CR0-CR31 in increments of 1
                            assert (sv_extra >> 2) == 0, \
                                "scalar CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as scalar
                            sv_extra = sv_extra & 0b11
                        else:
                            # range is CR0-CR127 in increments of 8
                            assert sv_extra & 0b11 == 0, \
                                "vector CR %s cannot fit into EXTRA2 %s" % \
                                    (regname, str(extras[extra_idx]))
                            # all good: encode as vector (bit 3 set)
                            sv_extra = 0b100 | (sv_extra >> 2)

                    # reconstruct the actual 5-bit CR field
                    field = (field << 2) | cr_subfield

                # capture the extra field info
                print ("=>", "%5s" % bin(sv_extra), field)
                extras[extra_idx] = sv_extra

                # append altered field value to v3.0b
                v30b_newfields.append(str(field))

            print ("new v3.0B fields", v30b_op, v30b_newfields)
            print ("extras", extras)

            # rright.  now we have all the info. start creating SVP64 RM
            svp64_rm = 0b0

            # begin with EXTRA fields
            for idx, sv_extra in extras.items():
                if idx is None: continue
                # start at bit 10, work up 2/3 times EXTRA idx
                offs = 2 if etype == 'EXTRA2' else 3 # 2 or 3 bits
                svp64_rm |= sv_extra << (10+idx*offs)

            # parts of svp64_rm
            mmode = 0  # bit 0
            pmask = 0  # bits 1-3
            destwid = 0 # bits 4-5
            srcwid = 0 # bits 6-7
            subvl = 0   # bits 8-9
            smask = 0 # bits 16-18 but only for twin-predication
            mode = 0 # bits 19-23

            has_pmask = False
            has_smask = False

            saturation = None
            src_zero = 0
            dst_zero = 0
            sv_mode = None

            mapreduce = False
            mapreduce_crm = False
            mapreduce_svm = False

            predresult = False
            failfirst = False

            # ok let's start identifying opcode augmentation fields
            for encmode in opmodes:
                # predicate mask (dest)
                if encmode.startswith("m="):
                    pme = encmode
                    pmmode, pmask = decode_predicate(encmode[2:])
                    mmode = pmmode
                    has_pmask = True
                # predicate mask (src, twin-pred)
                elif encmode.startswith("sm="):
                    sme = encmode
                    smmode, smask = decode_predicate(encmode[3:])
                    mmode = smmode
                    has_smask = True
                # vec2/3/4
                elif encmode.startswith("vec"):
                    subvl = decode_subvl(encmode[3:])
                # elwidth
                elif encmode.startswith("ew="):
                    destwid = decode_elwidth(encmode[3:])
                elif encmode.startswith("sw="):
                    srcwid = decode_elwidth(encmode[3:])
                # saturation
                elif encmode == 'sats':
                    assert sv_mode is None
                    saturation = 1
                    sv_mode = 0b10
                elif encmode == 'satu':
                    assert sv_mode is None
                    sv_mode = 0b10
                    saturation = 0
                # predicate zeroing
                elif encmode == 'sz':
                    src_zero = 1
                elif encmode == 'dz':
                    dst_zero = 1
                # failfirst
                elif encmode.startswith("ff="):
                    assert sv_mode is None
                    sv_mode = 0b01
                    failfirst = decode_ffirst(encmode[3:])
                # predicate-result, interestingly same as fail-first
                elif encmode.startswith("pr="):
                    assert sv_mode is None
                    sv_mode = 0b11
                    predresult = decode_ffirst(encmode[3:])
                # map-reduce mode
                elif encmode == 'mr':
                    assert sv_mode is None
                    sv_mode = 0b00
                    mapreduce = True
                elif encmode == 'crm': # CR on map-reduce
                    assert sv_mode is None
                    sv_mode = 0b00
                    mapreduce_crm = True
                elif encmode == 'svm': # sub-vector mode
                    mapreduce_svm = True

            # construct the mode field, doing sanity-checking along the way

            if mapreduce_svm:
                assert sv_mode == 0b00, "sub-vector mode in mapreduce only"
                assert subvl != 0, "sub-vector mode not possible on SUBVL=1"

            # "normal" mode
            if sv_mode is None:
                mode |= (src_zero << 3) | (dst_zero << 4) # predicate zeroing

            # "mapreduce" modes
            elif sv_mode == 0b00:
                mode |= (0b1<<2) # sets mapreduce
                assert dst_zero == 0, "dest-zero not allowed in mapreduce mode"
                if mapreduce_crm:
                    mode |= (0b1<<4) # sets CRM mode
                    assert rc_mode, "CRM only allowed when Rc=1"
                # bit of weird encoding to jam zero-pred or SVM mode in.
                # SVM mode can be enabled only when SUBVL=2/3/4 (vec2/3/4)
                if subvl == 0:
                    mode |= (src_zero << 3) # predicate src-zeroing
                elif mapreduce_svm:
                    mode |= (1 << 3) # SVM mode

            # "failfirst" modes
            elif sv_mode == 0b01:
                assert dst_zero == 0, "dest-zero not allowed in failfirst mode"
                mode |= 0b01 # sets failfirst
                if failfirst == 'RC1':
                    mode |= (0b1<<4) # sets RC1 mode
                    mode |= (src_zero << 3) # predicate src-zeroing
                    assert rc_mode==False, "ffirst RC1 only possible when Rc=0"
                elif failfirst == '~RC1':
                    mode |= (0b1<<4) # sets RC1 mode...
                    mode |= (src_zero << 3) # predicate src-zeroing
                    mode |= (0b1<<2) # ... with inversion
                    assert rc_mode==False, "ffirst RC1 only possible when Rc=0"
                else:
                    assert src_zero == 0, "src-zero not allowed in ffirst BO"
                    assert rc_mode, "ffirst BO only possible when Rc=1"
                    mode |= (failfirst << 2) # set BO

            # "saturation" modes
            elif sv_mode == 0b10:
                mode |= 0b10 # sets saturation mode
                mode |= (src_zero << 3) | (dst_zero << 4) # predicate zeroing
                mode |= (saturation<<2) # sets signed/unsigned saturation

            # sanity-check that 2Pred mask is same mode
            if has_pmask and has_smask:
                assert smmode == pmmode, \
                    "predicate masks %s and %s must be same reg type" % \
                        (pme, sme)

            # sanity-check that twin-predication mask only specified in 2P mode
            if ptype == '1P':
                assert has_smask == False, \
                    "source-mask can only be specified on Twin-predicate ops"

            # put in predicate masks into svp64_rm
            if ptype == '2P':
                svp64_rm |= (smask << 16) # source pred: bits 16-18
            svp64_rm |= (mmode)           # mask mode: bit 0
            svp64_rm |= (pmask << 1)      # 1-pred: bits 1-3

            # and subvl
            svp64_rm += (subvl << 8)      # subvl: bits 8-9

            # put in elwidths
            svp64_rm += (srcwid << 6)      # srcwid: bits 6-7
            svp64_rm += (destwid << 4)     # destwid: bits 4-5

            # nice debug printout. (and now for something completely different)
            # https://youtu.be/u0WOIwlXE9g?t=146
            print ("svp64_rm", hex(svp64_rm), bin(svp64_rm))
            print ("    mmode  0    :", bin(mmode))
            print ("    pmask  1-3  :", bin(pmask))
            print ("    dstwid 4-5  :", bin(destwid))
            print ("    srcwid 6-7  :", bin(srcwid))
            print ("    subvl  8-9  :", bin(subvl))
            print ("    mode   19-23:", bin(mode))
            offs = 2 if etype == 'EXTRA2' else 3 # 2 or 3 bits
            for idx, sv_extra in extras.items():
                if idx is None: continue
                start = (10+idx*offs)
                end = start + offs-1
                print ("    extra%d %2d-%2d:" % (idx, start, end),
                        bin(sv_extra))
            if ptype == '2P':
                print ("    smask  16-17:", bin(smask))
            print ()

        return res

if __name__ == '__main__':
    isa = SVP64(['slw 3, 1, 4',
                 'extsw 5, 3',
                 'sv.extsw 5, 3',
                 'sv.cmpi 5, 1, 3, 2',
                 'sv.setb 5, 31',
                 'sv.isel 64.v, 3, 2, 65.v',
                 'sv.setb/m=r3.sm=1<<r3 5, 31',
                 'sv.setb/vec2 5, 31',
                 'sv.setb/sw=8.ew=16 5, 31',
                 'sv.extsw./ff=eq 5, 31',
                 'sv.extsw./satu.sz.dz 5, 31',
                ])
    csvs = SVP64RM()
