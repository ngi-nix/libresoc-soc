"""JTAG interface

using Staf Verhaegen (Chips4Makers) wishbone TAP
"""

from collections import OrderedDict
from nmigen import (Module, Signal, Elaboratable, Cat)
from nmigen.cli import rtlil
from c4m.nmigen.jtag.tap import IOType
from soc.debug.dmi import  DMIInterface, DBGCore
from soc.debug.dmi2jtag import DMITAP

# map from pinmux to c4m jtag iotypes
iotypes = {'-': IOType.In,
           '+': IOType.Out,
           '>': IOType.TriOut,
           '*': IOType.InTriOut,
        }

scanlens = {IOType.In: 1,
           IOType.Out: 1,
           IOType.TriOut: 2,
           IOType.InTriOut: 3,
            }

def dummy_pinset():
    # sigh this needs to come from pinmux.
    gpios = []
    for i in range(16):
        gpios.append("%d*" % i)
    return {'uart': ['tx+', 'rx-'],
             'gpio': gpios,
             'i2c': ['sda*', 'scl+']}

# TODO: move to suitable location
class Pins:
    """declare a list of pins, including name and direction.  grouped by fn
    the pin dictionary needs to be in a reliable order so that the JTAG
    Boundary Scan is also in a reliable order
    """
    def __init__(self, pindict):
        self.io_names = OrderedDict()
        if isinstance(pindict, OrderedDict):
            self.io_names.update(pindict)
        else:
            keys = list(pindict.keys())
            keys.sort()
            for k in keys:
                self.io_names[k] = pindict[k]

    def __iter__(self):
        # start parsing io_names and enumerate them to return pin specs
        scan_idx = 0
        for fn, pins in self.io_names.items():
            for pin in pins:
                # decode the pin name and determine the c4m jtag io type
                name, pin_type = pin[:-1], pin[-1]
                iotype = iotypes[pin_type]
                pin_name = "%s_%s" % (fn, name)
                yield (fn, name, iotype, pin_name, scan_idx)
                scan_idx += scanlens[iotype] # inc boundary reg scan offset


class JTAG(DMITAP, Pins):
    # 32-bit data width here so that it matches with litex
    def __init__(self, pinset, wb_data_wid=32):
        DMITAP.__init__(self, ir_width=4)
        Pins.__init__(self, pinset)

        # enumerate pin specs and create IOConn Records.
        # we store the boundary scan register offset in the IOConn record
        self.ios = [] # these are enumerated in external_ports
        self.scan_len = 0
        for fn, pin, iotype, pin_name, scan_idx in list(self):
            io = self.add_io(iotype=iotype, name=pin_name)
            io._scan_idx = scan_idx # hmm shouldn't really do this
            self.scan_len += scan_idx # record full length of boundary scan
            self.ios.append(io)

        # this is redundant.  or maybe part of testing, i don't know.
        self.sr = self.add_shiftreg(ircode=4, length=3)

        # create and connect wishbone
        self.wb = self.add_wishbone(ircodes=[5, 6, 7], features={'err'},
                                   address_width=30, data_width=wb_data_wid,
                                   granularity=8, # 8-bit wide
                                   name="jtag_wb")

        # create DMI2JTAG (goes through to dmi_sim())
        self.dmi = self.add_dmi(ircodes=[8, 9, 10])

        # use this for enable/disable of parts of the ASIC.
        # XXX make sure to add the _en sig to en_sigs list
        self.wb_icache_en = Signal(reset=1)
        self.wb_dcache_en = Signal(reset=1)
        self.wb_sram_en = Signal(reset=1)
        self.en_sigs = en_sigs = Cat(self.wb_icache_en, self.wb_dcache_en,
                                     self.wb_sram_en)
        self.sr_en = self.add_shiftreg(ircode=11, length=len(en_sigs))

    def elaborate(self, platform):
        m = super().elaborate(platform)
        m.d.comb += self.sr.i.eq(self.sr.o) # loopback as part of test?

        # provide way to enable/disable wishbone caches and SRAM
        # just in case of issues
        # see https://bugs.libre-soc.org/show_bug.cgi?id=520
        with m.If(self.sr_en.oe):
            m.d.sync += self.en_sigs.eq(self.sr_en.o)
        # also make it possible to read the enable/disable current state
        with m.If(self.sr_en.ie):
            m.d.comb += self.sr_en.i.eq(self.en_sigs)

        # create a fake "stall"
        #wb = self.wb
        #m.d.comb += wb.stall.eq(wb.cyc & ~wb.ack) # No burst support

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
    pinset = dummy_pinset()
    dut = JTAG(pinset)

    vl = rtlil.convert(dut)
    with open("test_jtag.il", "w") as f:
        f.write(vl)

