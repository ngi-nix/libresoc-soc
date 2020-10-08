"""DMI 2 JTAG test

based on Staf Verhaegen (Chips4Makers) wishbone TAP
"""

import sys
from nmigen import (Module, Signal, Elaboratable, Const)
from c4m.nmigen.jtag.tap import TAP, IOType
from c4m.nmigen.jtag.bus import Interface as JTAGInterface
from soc.debug.dmi import DMIInterface, DBGCore
from soc.debug.test.dmi_sim import dmi_sim
from soc.debug.dmi2jtag import DMITAP
from soc.debug.test.jtagremote import JTAGServer, JTAGClient

from nmigen_soc.wishbone.sram import SRAM
from nmigen import Memory, Signal, Module

from nmigen.back.pysim import Simulator, Delay, Settle, Tick
from nmutil.util import wrap
from soc.debug.jtagutils import (jtag_read_write_reg,
                                 jtag_srv, jtag_set_reset)

# JTAG-ircodes for accessing DMI
DMI_ADDR = 8
DMI_READ = 9
DMI_WRRD = 10

# JTAG-ircodes for accessing Wishbone
WB_ADDR = 5
WB_READ = 6
WB_WRRD = 7


def jtag_sim(dut):

    ####### JTAGy stuff (IDCODE) ######

    # read idcode
    yield from jtag_set_reset(dut)
    idcode = yield from jtag_read_write_reg(dut, 0b1, 32)
    print ("idcode", hex(idcode))
    assert idcode == 0x18ff

    ####### JTAG to DMI ######

    # write DMI address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, DBGCore.CTRL)

    # read DMI CTRL register
    status = yield from jtag_read_write_reg(dut, DMI_READ, 64)
    print ("dmi ctrl status", hex(status))
    assert status == 4

    # write DMI address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, 0)

    # write DMI CTRL register
    status = yield from jtag_read_write_reg(dut, DMI_WRRD, 64, 0b101)
    print ("dmi ctrl status", hex(status))
    assert status == 4 # returned old value (nice! cool feature!)

    # write DMI address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, DBGCore.CTRL)

    # read DMI CTRL register
    status = yield from jtag_read_write_reg(dut, DMI_READ, 64)
    print ("dmi ctrl status", hex(status))
    assert status == 5

    # write DMI MSR address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, DBGCore.MSR)

    # read DMI MSR register
    msr = yield from jtag_read_write_reg(dut, DMI_READ, 64)
    print ("dmi msr", hex(msr))
    assert msr == 0xdeadbeef

    ####### JTAG to Wishbone ######

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 16, 0x18)

    # write/read wishbone data
    data = yield from jtag_read_write_reg(dut, WB_WRRD, 16, 0xfeef)
    print ("wb write", hex(data))

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 16, 0x18)

    # write/read wishbone data
    data = yield from jtag_read_write_reg(dut, WB_READ, 16, 0)
    print ("wb read", hex(data))

    ####### done - tell dmi_sim to stop (otherwise it won't) ########

    dut.stop = True


if __name__ == '__main__':
    dut = DMITAP(ir_width=4)
    dut.stop = False

    # set up client-server on port 44843-something
    dut.s = JTAGServer()
    if len(sys.argv) != 2 or sys.argv[1] != 'server':
        dut.c = JTAGClient()
        dut.s.get_connection()
    else:
        dut.s.get_connection(None) # block waiting for connection

    # rather than the client access the JTAG bus directly
    # create an alternative that the client sets
    dut.cbus = JTAGInterface()

    iotypes = (IOType.In, IOType.Out, IOType.TriOut, IOType.InTriOut)
    ios = [dut.add_io(iotype=iotype) for iotype in iotypes]
    dut.sr = dut.add_shiftreg(ircode=4, length=3) # test loopback register

    # create and connect wishbone SRAM (a quick way to do WB test)
    dut.wb = dut.add_wishbone(ircodes=[WB_ADDR, WB_READ, WB_WRRD],
                               address_width=16, data_width=16)
    memory = Memory(width=16, depth=16)
    sram = SRAM(memory=memory, bus=dut.wb)

    # create DMI2JTAG (goes through to dmi_sim())
    dut.dmi = dut.add_dmi(ircodes=[DMI_ADDR, DMI_READ, DMI_WRRD])

    m = Module()
    m.submodules.ast = dut
    m.submodules.sram = sram
    m.d.comb += dut.sr.i.eq(dut.sr.o) # loopback

    sim = Simulator(m)
    sim.add_clock(1e-6, domain="sync")      # standard clock

    sim.add_sync_process(wrap(jtag_srv(dut))) # jtag server
    if len(sys.argv) != 2 or sys.argv[1] != 'server':
        sim.add_sync_process(wrap(jtag_sim(dut))) # actual jtag tester
    else:
        print ("running server only as requested, use openocd remote to test")
    sim.add_sync_process(wrap(dmi_sim(dut)))  # handles (pretends to be) DMI

    with sim.write_vcd("dmi2jtag_test_srv.vcd"):
        sim.run()
