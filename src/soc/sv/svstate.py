# SPDX-License-Identifier: LGPLv3+
# Copyright (C) 2021 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Funded by NLnet http://nlnet.nl
"""SVSATE SPR Record.  actually a peer of PC (CIA/NIA) and MSR

https://libre-soc.org/openpower/sv/sprs/

| Field | Name     | Description           |
| ----- | -------- | --------------------- |
| 0:6   | maxvl    | Max Vector Length     |
| 7:13  |    vl    | Vector Length         |
| 14:20 | srcstep  | for srcstep = 0..VL-1 |
| 21:27 | dststep  | for dststep = 0..VL-1 |
| 28:29 | subvl    | Sub-vector length     |
| 30:31 | svstep   | for svstep = 0..SUBVL-1  |
"""

from nmutil.iocontrol import RecordObject
from nmigen import Signal


# In nMigen, Record order is from LSB to MSB
class SVSTATERec(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.svstep = Signal(2)
        self.subvl = Signal(2)
        self.dststep = Signal(7)
        self.srcstep = Signal(7)
        self.vl = Signal(7)
        self.maxvl = Signal(7)
