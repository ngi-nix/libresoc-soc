# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl

from soc.decoder.power_enums import get_csv, find_wiki_dir
import os

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

        return v30b

if __name__ == '__main__':
    isa = SVP64RM()
    minor_30 = isa.get_svp64_csv("minor_30.csv")
    for entry in minor_30:
        print (entry)
