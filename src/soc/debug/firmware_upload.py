"""JTAG Wishbone firmware upload program

to test, run "python3 debug/test/test_jtag_tap_srv.py server"

"""

import sys
from nmigen import (Module, Signal, Elaboratable, Const)
from c4m.nmigen.jtag.tap import TAP, IOType
from c4m.nmigen.jtag.bus import Interface as JTAGInterface
from soc.debug.dmi import DMIInterface, DBGCore
from soc.debug.test.dmi_sim import dmi_sim
from soc.debug.jtag import JTAG
from soc.debug.test.jtagremote import JTAGServer, JTAGClient

from nmigen_soc.wishbone.sram import SRAM
from nmigen import Memory, Signal, Module

from nmigen.back.pysim import Simulator, Delay, Settle, Tick
from nmutil.util import wrap
from soc.debug.jtagutils import (jtag_read_write_reg,
                                 jtag_srv, jtag_set_reset,
                                 jtag_set_ir, jtag_set_get_dr)

def test_pinset():
    return {
            # in, out, tri-out, tri-inout
            'test': ['io0-', 'io1+', 'io2>', 'io3*'],
           }


# JTAG-ircodes for accessing DMI
DMI_ADDR = 8
DMI_READ = 9
DMI_WRRD = 10

# JTAG-ircodes for accessing Wishbone
WB_ADDR = 5
WB_READ = 6
WB_WRRD = 7

# JTAG boundary scan reg addresses
BS_EXTEST = 0
BS_INTEST = 0
BS_SAMPLE = 2
BS_PRELOAD = 2


def jtag_sim(dut, firmware):

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
    yield from jtag_read_write_reg(dut, WB_ADDR, 64, 0)

    # write/read wishbone data
    for val in firmware:
        data = yield from jtag_read_write_reg(dut, WB_WRRD, 64, val)
        print ("wb write", hex(data))

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 64, 0)

    # confirm data written
    for val in firmware:
        data = yield from jtag_read_write_reg(dut, WB_READ, 64, 0)
        print ("wb read", hex(data))

    ####### done - tell dmi_sim to stop (otherwise it won't) ########

    print ("jtag sim stopping")


if __name__ == '__main__':
    # rather than the client access the JTAG bus directly
    # create an alternative that the client sets
    class Dummy: pass
    cdut = Dummy()
    cdut.cbus = JTAGInterface()

    # set up client-server on port 44843-something
    cdut.c = JTAGClient()

    # take copy of ir_width and scan_len
    cdut._ir_width = 4

    flag = Signal()
    m = Module()
    m.d.sync += flag.eq(~flag) # get us a "sync" domain

    sim = Simulator(m)
    sim.add_clock(1e-6, domain="sync")      # standard clock

    data = [0x01, 0x02] # list of 64-bit words
    sim.add_sync_process(wrap(jtag_sim(cdut, data))) 

    with sim.write_vcd("jtag_firmware_upload.vcd"):
        sim.run()
