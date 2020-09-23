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

from migen.fhdl.structure import _Fragment
from litex.build.generic_platform import (GenericPlatform, Pins,
                                        Subsignal, IOStandard, Misc,
                                        )
import os

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # CLK/RST: 2 pins
    ("sys_clk", 0, Pins("G2"), IOStandard("LVCMOS33")),
    ("sys_rst",   0, Pins("R1"), IOStandard("LVCMOS33")),

    # JTAG0: 4 pins
    ("jtag", 0,
        Subsignal("tms", Pins("Z1"), IOStandard("LVCMOS33")),
        Subsignal("tck", Pins("Z2"), IOStandard("LVCMOS33")),
        Subsignal("tdi", Pins("Z3"), IOStandard("LVCMOS33")),
        Subsignal("tdo", Pins("Z4"), IOStandard("LVCMOS33")),
    ),

    # I2C0: 2 pins
    ("i2c", 0,
        Subsignal("scl", Pins("L4"), IOStandard("LVCMOS33")),
        Subsignal("sda", Pins("M1"), IOStandard("LVCMOS33"))
    ),

    # UART0: 2 pins
    ("serial", 0,
        Subsignal("tx", Pins("L4"), IOStandard("LVCMOS33")),
        Subsignal("rx", Pins("M1"), IOStandard("LVCMOS33"))
    ),

    # UART1: 2 pins
    ("serial", 1,
        Subsignal("tx", Pins("L4"), IOStandard("LVCMOS33")),
        Subsignal("rx", Pins("M1"), IOStandard("LVCMOS33"))
    ),

    # SPI0: 4 pins
    ("spi_master", 0,
        Subsignal("clk",  Pins("J1")),
        Subsignal("mosi", Pins("J3"), Misc("PULLMODE=UP")),
        Subsignal("cs_n", Pins("H1"), Misc("PULLMODE=UP")),
        Subsignal("miso", Pins("K2"), Misc("PULLMODE=UP")),
        Misc("SLEWRATE=FAST"),
        IOStandard("LVCMOS33"),
    ),

    # SPICARD0: 4 pins
    ("spisdcard", 0,
        Subsignal("clk",  Pins("J1")),
        Subsignal("mosi", Pins("J3"), Misc("PULLMODE=UP")),
        Subsignal("cs_n", Pins("H1"), Misc("PULLMODE=UP")),
        Subsignal("miso", Pins("K2"), Misc("PULLMODE=UP")),
        Misc("SLEWRATE=FAST"),
        IOStandard("LVCMOS33"),
    ),

    # SDCARD0: 6 pins
    ("sdcard", 0,
        Subsignal("clk",  Pins("J1")),
        Subsignal("cmd",  Pins("J3"), Misc("PULLMODE=UP")),
        Subsignal("data", Pins("K2 K1 H2 H1"), Misc("PULLMODE=UP")),
        Misc("SLEWRATE=FAST"),
        IOStandard("LVCMOS33"),
    ),

    # SDRAM: 39 pins
    ("sdram_clock", 0, Pins("F19"), IOStandard("LVCMOS33")),
    ("sdram", 0,
        Subsignal("a",     Pins(
            "M20 M19 L20 L19 K20 K19 K18 J20",
            "J19 H20 N19 G20 G19")),
        Subsignal("dq",    Pins(
            "J16 L18 M18 N18 P18 T18 T17 U20",
            "E19 D20 D19 C20 E18 F18 J18 J17")),
        Subsignal("we_n",  Pins("T20")),
        Subsignal("ras_n", Pins("R20")),
        Subsignal("cas_n", Pins("T19")),
        Subsignal("cs_n",  Pins("P20")),
        Subsignal("cke",   Pins("F20")),
        Subsignal("ba",    Pins("P19 N20")),
        Subsignal("dm",    Pins("U19 E20")),
        IOStandard("LVCMOS33"),
        Misc("SLEWRATE=FAST"),
    ),

    # PWM: 2 pins
    ("pwm", 0, Pins("P1"), IOStandard("LVCMOS33")),
    ("pwm", 1, Pins("P2"), IOStandard("LVCMOS33")),
]

if False:
    pinbank1 = []
    pinbank2 = []
    for i in range(8):
        pinbank1.append("X%d" % i)
        pinbank2.append("Y%d" % i)
    pins = ' '.join(pinbank1 + pinbank2)

    # 16 GPIOs
    _io.append( ("gpio", 16, Pins(pins), IOStandard("LVCMOS33")) )

pinsin = []
pinsout = []
for i in range(8):
    pinsin.append("X%d" % i)
    pinsout.append("Y%d" % i)
pinsin = ' '.join(pinsin)
pinsout = ' '.join(pinsout)

# GPIO in: 8 pins
_io.append( ("gpio_in", 8, Pins(pinsin), IOStandard("LVCMOS33")) )
# GPIO out: 8 pins
_io.append( ("gpio_out", 8, Pins(pinsout), IOStandard("LVCMOS33")) )

# EINT: 3 pins
_io.append( ("eint", 3, Pins("E0 E1 E2"), IOStandard("LVCMOS33")) )

# Platform -----------------------------------------------------------------------------------------

class LS180Platform(GenericPlatform):
    default_clk_name   = "sys_clk"
    default_clk_period = 1e9/50e6

    def __init__(self, device="LS180", **kwargs):
        assert device in ["LS180"]
        GenericPlatform.__init__(self, device, _io, **kwargs)

    def build(self, fragment,
                    build_dir      = "build",
                    build_name     = "top",
                    run            = True,
                    timingstrict   = True,
                    **kwargs):

        platform = self

        # Create build directory
        os.makedirs(build_dir, exist_ok=True)
        cwd = os.getcwd()
        os.chdir(build_dir)

        # Finalize design
        if not isinstance(fragment, _Fragment):
            fragment = fragment.get_fragment()
        platform.finalize(fragment)

        # Generate verilog
        v_output = platform.get_verilog(fragment, name=build_name, **kwargs)
        named_sc, named_pc = platform.resolve_signals(v_output.ns)
        v_file = build_name + ".v"
        v_output.write(v_file)
        platform.add_source(v_file)

        os.chdir(cwd)

        return v_output.ns

    def do_finalize(self, fragment):
        super().do_finalize(fragment)
        return
        self.add_period_constraint(self.lookup_request("clk", loose=True),
                                   1e9/50e6)
