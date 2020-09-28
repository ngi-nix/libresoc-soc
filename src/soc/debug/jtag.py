"""JTAG interface

using Staf Verhaegen (Chips4Makers) wishbone TAP
"""

from nmigen import (Module, Signal, Elaboratable)
from nmigen.cli import rtlil
from c4m.nmigen.jtag.tap import IOType
from soc.debug.dmi import  DMIInterface, DBGCore
from soc.debug.dmi2jtag import DMITAP

# map from pinmux to c4m jtag iotypes
iotypes = {'-': IOType.In,
           '+': IOType.Out,
           '*': IOType.InTriOut}


# TODO: move to suitable location
class Pins:
    """declare a list of pins, including name and direction.  grouped by fn
    """
    def __init__(self):
        # sigh this needs to come from pinmux.
        gpios = []
        for i in range(16):
            gpios.append("gpio%d*" % i)
        self.io_names = {'uart': ['tx+', 'rx-'], 'gpio': gpios}

    def __iter__(self):
        # start parsing io_names and enumerate them to return pin specs
        for fn, pins in self.io_names.items():
            for pin in pins:
                # decode the pin name and determine the c4m jtag io type
                name, pin_type = pin[:-1], pin[-1]
                iotype = iotypes[pin_type]
                pin_name = "%s_%s" % (fn, name)
                yield (fn, name, iotype, pin_name)


class JTAG(DMITAP, Pins):
    def __init__(self):
        DMITAP.__init__(self, ir_width=4)
        Pins.__init__(self)

        # enumerate pin specs and create IOConn Records.
        self.ios = [] # these are enumerated in external_ports
        for fn, pin, iotype, pin_name in list(self):
            io = self.add_io(iotype=iotype, name=pin_name)
            self.ios.append(io)

        # this is redundant.  or maybe part of testing, i don't know.
        self.sr = self.add_shiftreg(ircode=4, length=3)

        # create and connect wishbone 
        self.wb = self.add_wishbone(ircodes=[5, 6, 7],
                                   address_width=29, data_width=64,
                                   name="jtag_wb")

        # create DMI2JTAG (goes through to dmi_sim())
        self.dmi = self.add_dmi(ircodes=[8, 9, 10])

    def elaborate(self, platform):
        m = super().elaborate(platform)
        m.d.comb += self.sr.i.eq(self.sr.o) # loopback as part of test?
        return m

    def external_ports(self):
        """create a list of ports that goes into the top level il (or verilog)
        """
        ports = super().external_ports()           # gets JTAG signal names
        ports += list(self.wb.fields.values())     # wishbone signals
        for io in self.ios:
            ports += list(io.core.fields.values()) # io "core" signals
            ports += list(io.pad.fields.values())  # io "pad" signals"
        return ports


if __name__ == '__main__':
    dut = JTAG()

    vl = rtlil.convert(dut)
    with open("test_jtag.il", "w") as f:
        f.write(vl)

