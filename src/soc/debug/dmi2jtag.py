"""DMI 2 JTAG

based on Staf Verhaegen (Chips4Makers) wishbone TAP
"""

from nmigen import (Module, Signal, Elaboratable, Const)
from nmigen.cli import rtlil
from c4m.nmigen.jtag.tap import TAP, IOType

from soc.bus.sram import SRAM
from nmigen import Memory, Signal, Module

from nmigen.back.pysim import Simulator, Delay, Settle, Tick
from nmutil.util import wrap


# JTAG to DMI interface
#
# DMI bus
#
#  clk : |   |   |   |    | | |
#  req : ____/------------\_____
#  addr: xxxx<            >xxxxx
#  dout: xxxx<            >xxxxx
#  wr  : xxxx<            >xxxxx
#  din : xxxxxxxxxxxx<      >xxx
#  ack : ____________/------\___
#
#  * addr/dout set along with req, can be latched on same cycle by slave
#  * ack & din remain up until req is dropped by master, the slave must
#    provide a stable output on din on reads during that time.
#  * req remains low at until at least one sysclk after ack seen down.


class DMITAP(TAP):

    def external_ports(self):
        return [self.bus.tdo, self.bus.tdi, self.bus.tms, self.bus.tck]


if __name__ == '__main__':
    dut = DMITAP(ir_width=4)
    iotypes = (IOType.In, IOType.Out, IOType.TriOut, IOType.InTriOut)
    ios = [dut.add_io(iotype=iotype) for iotype in iotypes]
    dut.sr = dut.add_shiftreg(ircode=4, length=3) # test loopback register

    # create and connect wishbone SRAM (a quick way to do WB test)
    dut.wb = dut.add_wishbone(ircodes=[5, 6, 7], features={'err'},
                               address_width=16, data_width=16)

    # create DMI2JTAG (goes through to dmi_sim())
    dut.dmi = dut.add_dmi(ircodes=[8, 9, 10])

    vl = rtlil.convert(dut)
    with open("test_dmi2jtag.il", "w") as f:
        f.write(vl)

