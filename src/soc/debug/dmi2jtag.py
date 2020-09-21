"""DMI 2 JTAG

based on Staf Verhaegen (Chips4Makers) wishbone TAP
"""

from nmigen import (Module, Signal, Elaboratable, Const)
from nmigen.cli import rtlil
from c4m.nmigen.jtag.tap import TAP, IOType
from soc.debug.dmi import  DMIInterface, DBGCore

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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dmis = []

    def elaborate(self, platform):
        m = super().elaborate(platform)
        self._elaborate_dmis(m)
        return m

    def add_dmi(self, *, ircodes, address_width=8, data_width=64,
                     domain="sync", name=None):
        """Add a DMI interface

        * writing to DMIADDR will automatically trigger a DMI READ.
          the DMI address does not alter (so writes can be done at that addr)
        * reading from DMIREAD triggers a DMI READ at the current DMI addr
          the address is automatically incremented by 1 after.
        * writing to DMIWRITE triggers a DMI WRITE at the current DMI addr
          the address is automatically incremented by 1 after.

        Parameters:
        -----------
        ircodes: sequence of three integer for the JTAG IR codes;
                 they represent resp. DMIADDR, DMIREAD and DMIWRITE.
                 First code has a shift register of length 'address_width',
                 the two other codes share a shift register of length
                data_width.

        address_width: width of the address
        data_width: width of the data

        Returns:
        dmi: soc.debug.dmi.DMIInterface
            The DMI interface
        """
        if len(ircodes) != 3:
            raise ValueError("3 IR Codes have to be provided")

        if name is None:
            name = "dmi" + str(len(self._dmis))

        # add 2 shift registers: one for addr, one for data.
        sr_addr = self.add_shiftreg(ircode=ircodes[0], length=address_width,
                                     domain=domain, name=name+"_addrsr")
        sr_data = self.add_shiftreg(ircode=ircodes[1:], length=data_width,
                                    domain=domain, name=name+"_datasr")

        dmi = DMIInterface(name=name)
        self._dmis.append((sr_addr, sr_data, dmi, domain))

        return dmi

    def _elaborate_dmis(self, m):
        for sr_addr, sr_data, dmi, domain in self._dmis:
            cd = m.d[domain]
            m.d.comb += sr_addr.i.eq(dmi.addr_i)

            with m.FSM(domain=domain) as ds:

                # detect mode based on whether jtag addr or data read/written
                with m.State("IDLE"):
                    with m.If(sr_addr.oe): # DMIADDR code
                        cd += dmi.addr_i.eq(sr_addr.o)
                        m.next = "READ"
                    with m.Elif(sr_data.oe[0]): # DMIREAD code
                        # If data is
                        cd += dmi.addr_i.eq(dmi.addr_i + 1)
                        m.next = "READ"
                    with m.Elif(sr_data.oe[1]): # DMIWRITE code
                        cd += dmi.din.eq(sr_data.o)
                        m.next = "WRITE"

                # req_i raises for 1 clock
                with m.State("READ"):
                    m.next = "READACK"

                # wait for read ack
                with m.State("READACK"):
                    with m.If(dmi.ack_o):
                        # Store read data in sr_data.i hold till next read
                        cd += sr_data.i.eq(dmi.dout)
                        m.next = "IDLE"

                # req_i raises for 1 clock
                with m.State("WRITE"):
                    m.next = "WRITEACK"

                # wait for write ack
                with m.State("WRITEACK"):
                    with m.If(dmi.ack_o):
                        cd += dmi.addr_i.eq(dmi.addr_i + 1)
                        m.next = "IDLE"
                        #m.next = "READ" - for readwrite

                # set DMI req and write-enable based on ongoing FSM states
                m.d.comb += [
                    dmi.req_i.eq(ds.ongoing("READ") | ds.ongoing("WRITE")),
                    dmi.we_i.eq(ds.ongoing("WRITE")),
                ]


def tms_state_set(dut, bits):
    for bit in bits:
        yield dut.bus.tck.eq(1)
        yield dut.bus.tms.eq(bit)
        yield
        yield dut.bus.tck.eq(0)
        yield
    yield dut.bus.tms.eq(0)


def tms_data_getset(dut, tms, d_len, d_in=0):
    res = 0
    yield dut.bus.tms.eq(tms)
    for i in range(d_len):
        tdi = 1 if (d_in & (1<<i)) else 0
        yield dut.bus.tck.eq(1)
        res |= (1<<i) if (yield dut.bus.tdo) else 0
        yield
        yield dut.bus.tdi.eq(tdi)
        yield dut.bus.tck.eq(0)
        yield
    yield dut.bus.tdi.eq(0)
    yield dut.bus.tms.eq(0)

    return res


def jtag_set_reset(dut):
    yield from tms_state_set(dut, [1, 1, 1, 1, 1])

def jtag_set_shift_dr(dut):
    yield from tms_state_set(dut, [1, 0, 0])

def jtag_set_shift_ir(dut):
    yield from tms_state_set(dut, [1, 1, 0])

def jtag_set_run(dut):
    yield from tms_state_set(dut, [0])

def jtag_set_idle(dut):
    yield from tms_state_set(dut, [1, 1, 0])


def jtag_read_write_reg(dut, addr, d_len, d_in=0):
    yield from jtag_set_run(dut)
    yield from jtag_set_shift_ir(dut)
    yield from tms_data_getset(dut, 0, dut._ir_width, addr)
    yield from jtag_set_idle(dut)

    yield from jtag_set_shift_dr(dut)
    result = yield from tms_data_getset(dut, 0, d_len, d_in)
    yield from jtag_set_idle(dut)
    return result


stop = False

def dmi_sim(dut):
    global stop

    ctrl_reg = 0b100 # terminated

    dmi = dut.dmi
    while not stop:
        # wait for req
        req = yield dmi.req_i
        if req == 0:
            yield
            continue
        print ("dmi req", req)

        # check read/write and address
        wen = yield dmi.we_i
        addr = yield dmi.addr_i
        print ("dmi wen, addr", wen, addr)
        if addr == DBGCore.CTRL and wen == 0:
            yield dmi.dout.eq(ctrl_reg)
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)
        elif addr == DBGCore.CTRL and wen == 1:
            ctrl_reg = (yield dmi.din)
            print ("write ctrl reg", ctrl_reg)
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)
        else:
            # do nothing but just ack it
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)

# JTAG-ircodes for accessing DMI
DMI_ADDR = 5
DMI_READ = 6
DMI_WRITE = 7

def jtag_sim(dut):

    if True:
        # read idcode
        yield from jtag_set_reset(dut)
        idcode = yield from jtag_read_write_reg(dut, 0b1, 32)
        print ("idcode", hex(idcode))
        assert idcode == 0x18ff

    # write DMI address
    yield from jtag_read_write_reg(dut, 0b101, 8, DBGCore.CTRL)

    # read DMI CTRL register
    status = yield from jtag_read_write_reg(dut, 0b110, 64)
    print ("dmi ctrl status", hex(status))

    # write DMI address
    yield from jtag_read_write_reg(dut, 0b101, 8, 0)

    # write DMI CTRL register
    status = yield from jtag_read_write_reg(dut, 0b111, 64, 0b101)
    print ("dmi ctrl status", hex(status))

    # write DMI address
    yield from jtag_read_write_reg(dut, 0b1010, 8, DBGCore.CTRL)

    # read DMI CTRL register
    status = yield from jtag_read_write_reg(dut, 0b110, 64)
    print ("dmi ctrl status", hex(status))

    for i in range(64):
        yield

    global stop
    stop = True

if __name__ == '__main__':
    dut = DMITAP(ir_width=4)
    iotypes = (IOType.In, IOType.Out, IOType.TriOut, IOType.InTriOut)
    ios = [dut.add_io(iotype=iotype) for iotype in iotypes]
    dut.sr = dut.add_shiftreg(ircode=4, length=3) # test loopback register
    dut.dmi = dut.add_dmi(ircodes=[DMI_ADDR, DMI_READ, DMI_WRITE])

    m = Module()
    m.submodules.ast = dut
    m.d.comb += dut.sr.i.eq(dut.sr.o) # loopback

    sim = Simulator(m)
    sim.add_clock(1e-6, domain="sync")      # standard clock

    sim.add_sync_process(wrap(jtag_sim(dut)))
    sim.add_sync_process(wrap(dmi_sim(dut)))

    with sim.write_vcd("dmi2jtag_test.vcd"):
        sim.run()


