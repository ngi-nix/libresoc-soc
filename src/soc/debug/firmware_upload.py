"""JTAG Wishbone firmware upload program

to test, run "python3 debug/test/test_jtag_tap_srv.py server"

"""

import sys
from nmigen import (Module, Signal, Elaboratable, Const)
from c4m.nmigen.jtag.tap import TAP, IOType
from c4m.nmigen.jtag.bus import Interface as JTAGInterface
from soc.debug.dmi import DMIInterface, DBGCore, DBGStat, DBGCtrl
from soc.debug.test.dmi_sim import dmi_sim
from soc.debug.jtag import JTAG
from soc.debug.test.jtagremote import JTAGServer, JTAGClient

from soc.bus.sram import SRAM
from nmigen import Memory, Signal, Module

from nmigen.back.pysim import Simulator, Delay, Settle, Tick
from nmutil.util import wrap
from soc.debug.jtagutils import (jtag_read_write_reg,
                                 jtag_srv, jtag_set_reset,
                                 jtag_set_ir, jtag_set_get_dr)
from openpower.simulator.program import Program

def test_pinset():
    return {
            # in, out, tri-out, tri-inout
            'test': ['io0-', 'io1+', 'io2>', 'io3*'],
           }

def brev(n, width):
    b = '{:0{width}b}'.format(n, width=width)
    return int(b[::-1], 2)


# JTAG-ircodes for accessing DMI
DMI_ADDR = 8
DMI_READ = 9
DMI_WRRD = 10

# JTAG-ircodes for accessing Wishbone
WB_ADDR = 5
WB_READ = 6
WB_WRRD = 7


def read_dmi_addr(dut, dmi_addr):
    # write DMI address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, dmi_addr)

    # read DMI register
    return (yield from jtag_read_write_reg(dut, DMI_READ, 64))

def writeread_dmi_addr(dut, dmi_addr, data):
    # write DMI address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, dmi_addr)

    # write and read DMI register
    return (yield from jtag_read_write_reg(dut, DMI_WRRD, 64, data))


def jtag_sim(dut, firmware):
    """uploads firmware with the following commands:
    * read IDcode (to check)
    * set "stopped" and reset
    * repeat until confirmed "stopped"
    * upload data over wishbone
    * read data back and check it
    * issue cache flush command
    * issue "start" command
    """

    ####### JTAGy stuff (IDCODE) ######

    # read idcode
    yield from jtag_set_reset(dut)
    idcode = yield from jtag_read_write_reg(dut, 0b1, 32)
    print ("idcode", hex(idcode))
    assert idcode == 0x18ff

    ####### JTAG to DMI Setup (stop, reset) ######

    yield from read_dmi_addr(dut, DBGCore.CTRL)
    # read DMI CTRL reg
    status = yield from read_dmi_addr(dut, DBGCore.CTRL)
    print ("dmi ctrl status", bin(status))

    # write DMI CTRL register - STOP and RESET
    status = yield from writeread_dmi_addr(dut, DBGCore.CTRL,
                        (1<<DBGCtrl.STOP) |
                        (1<<DBGCtrl.RESET))
    print ("dmi ctrl status", hex(status))
    assert status == 0 # returned old value (nice! cool feature!)

    # read STAT and wait for "STOPPED"
    while True:
        status = yield from read_dmi_addr(dut, DBGCore.STAT)
        print ("dmi ctrl status", bin(status))
        if (status & (1<<DBGStat.STOPPED)) or (status & (1<<DBGStat.TERM)):
            break

    ####### JTAG to Wishbone - hard-coded 30-bit addr, 32-bit data ######

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 30, 0)

    # write/read wishbone data
    for val in firmware:
        data = yield from jtag_read_write_reg(dut, WB_WRRD, 32, val)
        print ("wb write", hex(val), hex(data))

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 30, 0)

    # confirm data written
    for val in firmware:
        data = yield from jtag_read_write_reg(dut, WB_READ, 32, val)
        print ("wb read", hex(val), hex(data))

    ####### JTAG to DMI Setup (IC-Reset, start) ######

    # write DMI CTRL register - ICRESET
    status = yield from writeread_dmi_addr(dut, DBGCore.CTRL,
                                           1<<DBGCtrl.ICRESET)
    print ("dmi ctrl status", hex(status))

    # write DMI CTRL register - START
    status = yield from writeread_dmi_addr(dut, DBGCore.CTRL,
                                           1<<DBGCtrl.START)
    print ("dmi ctrl status", hex(status))

    # read STAT just for info
    for i in range(4):
        status = yield from read_dmi_addr(dut, DBGCore.STAT)
        print ("dmi stat status", bin(status))

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

    # blinken lights...
    lst = """
    blink:
            li 3, 0
            lis 4, 1234
            lis 5, 5678
    .LBB0_1:
            std 3, 6780(4)
            mtctr 5
    .LBB0_2:
            bdnz .LBB0_2
            xori 3, 3, 1
            b .LBB0_1
    """
    # simple loop
    lst = ["addi 9, 0, 0x10",  # i = 16
           "addi 9,9,-1",    # i = i - 1
           "cmpi 2,1,9,12",     # compare 9 to value 12, store in CR2
           "bc 4,10,-16",        # branch if CR2 "test was != 12"
           'attn',
           ]

    data = []
    with Program(lst, False) as p:
        data = list(p.generate_instructions())
        for instruction in data:
            print (hex(instruction))

    sim.add_sync_process(wrap(jtag_sim(cdut, data))) 

    with sim.write_vcd("jtag_firmware_upload.vcd"):
        sim.run()
