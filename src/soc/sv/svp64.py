# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl
"""SVP64 RM (Remap) Record.  

https://libre-soc.org/openpower/sv/svp64/

| Field Name | Field bits | Description                            |
|------------|------------|----------------------------------------|
| MASKMODE   | `0`        | Execution (predication) Mask Kind      |
| MASK          | `1:3`      | Execution Mask                      |
| ELWIDTH       | `4:5`      | Element Width                       |
| ELWIDTH_SRC   | `6:7`      | Element Width for Source            |
| SUBVL         | `8:9`      | Sub-vector length                   |  
| EXTRA         | `10:18`    | context-dependent extra             |
| MODE          | `19:23`    | changes Vector behaviour            |
"""

from nmigen import Record

class SVP64Rec(Record):
    def __init__(self, name=None):
        Record.__init__([("mmode"   : 1),
                         ("mask"    : 3),
                         ("elwidth" : 2),
                         ("ewsrc"   : 2),
                         ("extra"   : 9),
                         ("mode"    : 5), name=name)

