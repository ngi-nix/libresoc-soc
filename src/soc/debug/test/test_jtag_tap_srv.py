"""DMI 2 JTAG test

based on Staf Verhaegen (Chips4Makers) wishbone TAP
"""

import sys
from nmigen import (Module, Signal, Elaboratable, Const)
from c4m.nmigen.jtag.tap import TAP, IOType
from c4m.nmigen.jtag.bus import Interface as JTAGInterface
from soc.debug.dmi import DMIInterface, DBGCore
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


def jtag_sim(dut, srv_dut):

    ####### JTAGy stuff (IDCODE) ######

    # read idcode
    yield from jtag_set_reset(dut)
    idcode = yield from jtag_read_write_reg(dut, 0b1, 32)
    print ("idcode", hex(idcode))
    assert idcode == 0x18ff

    ####### JTAG Boundary scan ######

    bslen = dut.scan_len
    print ("scan len", bslen)

    # sample test
    bs_actual = 0b100110
    yield srv_dut.ios[0].pad.i.eq(1)
    yield srv_dut.ios[1].core.o.eq(0)
    yield srv_dut.ios[2].core.o.eq(1)
    yield srv_dut.ios[2].core.oe.eq(1)
    yield srv_dut.ios[3].pad.i.eq(0)
    yield srv_dut.ios[3].core.o.eq(0)
    yield srv_dut.ios[3].core.oe.eq(1)
    yield

    bs = yield from jtag_read_write_reg(dut, BS_SAMPLE, bslen, bs_actual)
    print ("bs scan", bin(bs))
    yield

    print ("io0 pad.i", (yield srv_dut.ios[0].core.i))
    print ("io1 core.o", (yield srv_dut.ios[1].pad.o))
    print ("io2 core.o", (yield srv_dut.ios[2].pad.o))
    print ("io2 core.oe", (yield srv_dut.ios[2].pad.oe))
    print ("io3 core.i", (yield srv_dut.ios[3].core.i))
    print ("io3 pad.o", (yield srv_dut.ios[3].pad.o))
    print ("io3 pad.oe", (yield srv_dut.ios[3].pad.oe))

    assert (yield srv_dut.ios[0].core.i) == 1
    assert (yield srv_dut.ios[1].pad.o) == 0
    assert (yield srv_dut.ios[2].pad.o) == 1
    assert (yield srv_dut.ios[2].pad.oe) == 1
    assert (yield srv_dut.ios[3].core.i) == 0
    assert (yield srv_dut.ios[3].pad.o) == 0
    assert (yield srv_dut.ios[3].pad.oe) == 1

    # extest
    ir_actual = yield from jtag_set_ir(dut, BS_EXTEST)
    print ("ir extest", bin(ir_actual))
    yield

    print ("io0 pad.i", (yield srv_dut.ios[0].core.i))
    print ("io1 core.o", (yield srv_dut.ios[1].pad.o))
    print ("io2 core.o", (yield srv_dut.ios[2].pad.o))
    print ("io2 core.oe", (yield srv_dut.ios[2].pad.oe))
    print ("io3 core.i", (yield srv_dut.ios[3].core.i))
    print ("io3 pad.o", (yield srv_dut.ios[3].pad.o))
    print ("io3 pad.oe", (yield srv_dut.ios[3].pad.oe))

    assert (yield srv_dut.ios[0].core.i) == 0
    assert (yield srv_dut.ios[1].pad.o) == 1
    assert (yield srv_dut.ios[2].pad.o) == 0
    assert (yield srv_dut.ios[2].pad.oe) == 0
    assert (yield srv_dut.ios[3].core.i) == 1
    assert (yield srv_dut.ios[3].pad.o) == 1
    assert (yield srv_dut.ios[3].pad.oe) == 0

    # set pins
    bs_actual = 0b1011001
    yield srv_dut.ios[0].pad.i.eq(0)
    yield srv_dut.ios[1].core.o.eq(1)
    yield srv_dut.ios[2].core.o.eq(0)
    yield srv_dut.ios[2].core.oe.eq(0)
    yield srv_dut.ios[3].pad.i.eq(1)
    yield srv_dut.ios[3].core.o.eq(1)
    yield srv_dut.ios[3].core.oe.eq(0)
    yield

    bs = yield from jtag_set_get_dr(dut, bslen, bs_actual)
    print ("bs scan", bin(bs))
    yield

    print ("io0 pad.i", (yield srv_dut.ios[0].core.i))
    print ("io1 core.o", (yield srv_dut.ios[1].pad.o))
    print ("io2 core.o", (yield srv_dut.ios[2].pad.o))
    print ("io2 core.oe", (yield srv_dut.ios[2].pad.oe))
    print ("io3 core.i", (yield srv_dut.ios[3].core.i))
    print ("io3 pad.o", (yield srv_dut.ios[3].pad.o))
    print ("io3 pad.oe", (yield srv_dut.ios[3].pad.oe))

    assert (yield srv_dut.ios[0].core.i) == 1
    assert (yield srv_dut.ios[1].pad.o) == 0
    assert (yield srv_dut.ios[2].pad.o) == 1
    assert (yield srv_dut.ios[2].pad.oe) == 1
    assert (yield srv_dut.ios[3].core.i) == 0
    assert (yield srv_dut.ios[3].pad.o) == 0
    assert (yield srv_dut.ios[3].pad.oe) == 1

    # reset
    yield from jtag_set_reset(dut)
    print ("bs reset")
    yield

    print ("io0 pad.i", (yield srv_dut.ios[0].pad.i))
    print ("io1 core.o", (yield srv_dut.ios[1].core.o))
    print ("io2 core.o", (yield srv_dut.ios[2].core.o))
    print ("io2 core.oe", (yield srv_dut.ios[2].core.oe))
    print ("io3 core.i", (yield srv_dut.ios[3].core.i))
    print ("io3 pad.o", (yield srv_dut.ios[3].pad.o))
    print ("io3 pad.oe", (yield srv_dut.ios[3].pad.oe))

    assert (yield srv_dut.ios[0].core.i) == 0
    assert (yield srv_dut.ios[1].pad.o) == 1
    assert (yield srv_dut.ios[2].pad.o) == 0
    assert (yield srv_dut.ios[2].pad.oe) == 0
    assert (yield srv_dut.ios[3].core.i) == 1
    assert (yield srv_dut.ios[3].pad.o) == 1
    assert (yield srv_dut.ios[3].pad.oe) == 0

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
    assert status == 0

    # write DMI MSR address
    yield from jtag_read_write_reg(dut, DMI_ADDR, 8, DBGCore.MSR)

    # read DMI MSR register
    msr = yield from jtag_read_write_reg(dut, DMI_READ, 64)
    print ("dmi msr", hex(msr))
    assert msr == 0xdeadbeef

    ####### JTAG to Wishbone ######

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 64, 0x18)

    # write/read wishbone data
    data = yield from jtag_read_write_reg(dut, WB_WRRD, 64, 0xfeef)
    print ("wb write", hex(data))

    # write Wishbone address
    yield from jtag_read_write_reg(dut, WB_ADDR, 64, 0x18)

    # write/read wishbone data
    data = yield from jtag_read_write_reg(dut, WB_READ, 64, 0)
    print ("wb read", hex(data))

    ####### done - tell dmi_sim to stop (otherwise it won't) ########

    srv_dut.stop = True
    print ("jtag sim stopping")


if __name__ == '__main__':
    dut = JTAG(test_pinset(), wb_data_wid=64)
    dut.stop = False

    # rather than the client access the JTAG bus directly
    # create an alternative that the client sets
    class Dummy: pass
    cdut = Dummy()
    cdut.cbus = JTAGInterface()

    # set up client-server on port 44843-something
    dut.s = JTAGServer()
    if len(sys.argv) != 2 or sys.argv[1] != 'server':
        cdut.c = JTAGClient()
        dut.s.get_connection()
    else:
        dut.s.get_connection(None) # block waiting for connection

    # take copy of ir_width and scan_len
    cdut._ir_width = dut._ir_width
    cdut.scan_len = dut.scan_len

    memory = Memory(width=64, depth=16)
    sram = SRAM(memory=memory, bus=dut.wb)

    m = Module()
    m.submodules.ast = dut
    m.submodules.sram = sram

    sim = Simulator(m)
    sim.add_clock(1e-6, domain="sync")      # standard clock

    sim.add_sync_process(wrap(jtag_srv(dut))) # jtag server
    if len(sys.argv) != 2 or sys.argv[1] != 'server':
        sim.add_sync_process(wrap(jtag_sim(cdut, dut))) # actual jtag tester
    else:
        print ("running server only as requested, use openocd remote to test")
    sim.add_sync_process(wrap(dmi_sim(dut)))  # handles (pretends to be) DMI

    with sim.write_vcd("dmi2jtag_test_srv.vcd"):
        sim.run()
