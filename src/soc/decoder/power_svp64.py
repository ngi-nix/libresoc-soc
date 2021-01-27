# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl

from soc.decoder.power_enums import get_csv, find_wiki_dir
import os

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


def decode_extra(rm, prefix=''):
    # first turn the svp64 rm into a "by name" dict, recording
    # which position in the RM EXTRA it goes into
    # also: record if the src or dest was a CR, for sanity-checking
    # (elwidth overrides on CRs are banned)
    dest_reg_cr, src_reg_cr = False, False
    svp64_srcreg_byname = {}
    svp64_destreg_byname = {}
    for i in range(4):
        print (rm)
        rfield = rm[prefix+str(i)]
        if not rfield or rfield == '0':
            continue
        print ("EXTRA field", i, rfield)
        rfield = rfield.split(";") # s:RA;d:CR1 etc.
        for r in rfield:
            rtype = r[0]
            # TODO: ignoring s/d makes it impossible to do
            # LD/ST-with-update.
            r = r[2:] # ignore s: and d:
            if rtype == 'd':
                svp64_destreg_byname[r] = i # dest reg in EXTRA position 0-3
            else:
                svp64_srcreg_byname[r] = i # src reg in EXTRA position 0-3
            # check the regtype (if CR, record that)
            regtype = get_regtype(r)
            if regtype in ['CR_3bit', 'CR_5bit']:
                if rtype == 'd':
                    dest_reg_cr = True
                if rtype == 's':
                    src_reg_cr = True

    return dest_reg_cr, src_reg_cr, svp64_srcreg_byname, svp64_destreg_byname


# gets SVP64 ReMap information
class SVP64RM:
    def __init__(self):
        self.instrs = {}
        pth = find_wiki_dir()
        for fname in os.listdir(pth):
            if fname.startswith("RM") or fname.startswith("LDSTRM"):
                for entry in get_csv(fname):
                    self.instrs[entry['insn']] = entry


    def get_svp64_csv(self, fname):
        # first get the v3.0B entries
        v30b = get_csv(fname)

        # now add the RM fields (for each instruction)
        for entry in v30b:
            # dummy (blank) fields, first
            entry.update({'EXTRA0': '0', 'EXTRA1': '0', 'EXTRA2': '0',
                          'EXTRA3': '0',
                          'SV_Ptype': 'NONE', 'SV_Etype': 'NONE'})

            # is this SVP64-augmented?
            asmcode = entry['comment']
            if asmcode not in self.instrs:
                continue

            # start updating the fields, merge relevant info
            svp64 = self.instrs[asmcode]
            for k, v in {'EXTRA0': '0', 'EXTRA1': '1', 'EXTRA2': '2',
                          'EXTRA3': '3',
                          'SV_Ptype': 'Ptype', 'SV_Etype': 'Etype'}.items():
                entry[k] = svp64[v]

            # hmm, we need something more useful: a cross-association
            # of the in1/2/3 and CR in/out with the EXTRA0-3 fields
            decode = decode_extra(entry, "EXTRA")
            dest_reg_cr, src_reg_cr, svp64_src, svp64_dest = decode
            
            # now examine in1/2/3/out, create sv_in1/2/3/out
            for fname in ['in1', 'in2', 'in3', 'out']:
                regfield = entry[fname]
                extra_index = None
                if regfield == 'RA_OR_ZERO':
                    regfield = 'RA'
                print (asmcode, regfield, fname, svp64_dest, svp64_src)
                # find the reg in the SVP64 extra map
                if (fname == 'out' and regfield in svp64_dest):
                    extra_index = svp64_dest[regfield]
                if (fname != 'out' and regfield in svp64_src):
                    extra_index = svp64_src[regfield]
                # ta-daa, we know in1/2/3/out's bit-offset
                entry['sv_%s' % fname] = extra_index

        return v30b

if __name__ == '__main__':
    isa = SVP64RM()
    minor_30 = isa.get_svp64_csv("minor_30.csv")
    for entry in minor_30:
        print (entry)
