"""JTAG interface

using Staf Verhaegen (Chips4Makers) wishbone TAP
"""

from nmigen import (Module, Signal, Elaboratable)
from nmigen.cli import rtlil
from c4m.nmigen.jtag.tap import IOType
from soc.debug.dmi import  DMIInterface, DBGCore
from soc.debug.dmi2jtag import DMITAP


class JTAG(DMITAP):
    iotypes = (IOType.In, IOType.Out, IOType.TriOut, IOType.InTriOut)
    def __init__(self):
        super().__init__(ir_width=4)
        self.ios = [self.add_io(iotype=iotype) for iotype in self.iotypes]
        self.sr = self.add_shiftreg(ircode=4, length=3)

        # create and connect wishbone 
        self.wb = self.add_wishbone(ircodes=[5, 6, 7],
                                   address_width=29, data_width=64,
                                   name="jtag_wb")

        # create DMI2JTAG (goes through to dmi_sim())
        self.dmi = self.add_dmi(ircodes=[8, 9, 10])

    def elaborate(self, platform):
        return super().elaborate(platform)

    def external_ports(self):
        ports = super().external_ports()
        ports += list(self.wb.fields.values())
        return ports


if __name__ == '__main__':
    dut = JTAG()

    vl = rtlil.convert(dut)
    with open("test_jtag.il", "w") as f:
        f.write(vl)

