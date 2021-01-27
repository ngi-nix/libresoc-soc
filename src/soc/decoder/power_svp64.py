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



