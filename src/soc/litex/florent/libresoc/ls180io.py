#
# This file is part of LiteX.
#
# Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""ls180 ASIC platform

conceptually similar to the following:

* https://github.com/enjoy-digital/liteeth/blob/master/liteeth/gen.py
* https://github.com/enjoy-digital/litepcie/blob/master/litepcie/gen.py

Total I/O pins: 84.
Fits in a JEDEC QFP-100

"""

from litex.build.generic_platform import (GenericPlatform, Pins,
                                        Subsignal, IOStandard, Misc,
                                        )
import os

def make_uart(name, num):
    return (name, num,
        Subsignal("tx", Pins("L4"), IOStandard("LVCMOS33")),
        Subsignal("rx", Pins("M1"), IOStandard("LVCMOS33"))
    )

def make_gpio(name, num, n_gpio):
    pins = []
    for i in range(n_gpio):
        pins.append("X%d" % i)
    pins = ' '.join(pins)
    return (name, 0,
             Subsignal("i", Pins(pins), Misc("PULLMODE=UP")),
             Subsignal("o", Pins(pins), Misc("PULLMODE=UP")),
             Subsignal("oe", Pins(pins), Misc("PULLMODE=UP")),
            IOStandard("LVCMOS33"))

