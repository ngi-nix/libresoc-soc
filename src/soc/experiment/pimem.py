"""L0 Cache/Buffer

This first version is intended for prototyping and test purposes:
it has "direct" access to Memory.

The intention is that this version remains an integral part of the
test infrastructure, and, just as with minerva's memory arrangement,
a dynamic runtime config *selects* alternative memory arrangements
rather than *replaces and discards* this code.

Links:

* https://bugs.libre-soc.org/show_bug.cgi?id=216
* https://libre-soc.org/3d_gpu/architecture/memory_and_cache/

"""

from nmigen.compat.sim import run_simulation, Settle
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Elaboratable, Array, Cat
from nmutil.iocontrol import RecordObject
from nmigen.utils import log2_int
from nmigen.hdl.rec import Record, Layout

from nmutil.latch import SRLatch, latchregister
from soc.decoder.power_decoder2 import Data
from soc.decoder.power_enums import InternalOp
from soc.regfile.regfile import ortreereduce
from nmutil.util import treereduce

from soc.decoder.power_decoder2 import Data
#from nmutil.picker import PriorityPicker
from nmigen.lib.coding import PriorityEncoder
from soc.scoreboard.addr_split import LDSTSplitter
from soc.scoreboard.addr_match import LenExpand

# for testing purposes
from soc.experiment.testmem import TestMemory # TODO: replace with TMLSUI
# TODO: from soc.experiment.testmem import TestMemoryLoadStoreUnit

import unittest


class PortInterface(RecordObject):
    """PortInterface

    defines the interface - the API - that the LDSTCompUnit connects
    to.  note that this is NOT a "fire-and-forget" interface.  the
    LDSTCompUnit *must* be kept appraised that the request is in
    progress, and only when it has a 100% successful completion
    can the notification be given (busy dropped).

    The interface FSM rules are as follows:

    * if busy_o is asserted, a LD/ST is in progress.  further
      requests may not be made until busy_o is deasserted.

    * only one of is_ld_i or is_st_i may be asserted.  busy_o
      will immediately be asserted and remain asserted.

    * addr.ok is to be asserted when the LD/ST address is known.
      addr.data is to be valid on the same cycle.

      addr.ok and addr.data must REMAIN asserted until busy_o
      is de-asserted.  this ensures that there is no need
      for the L0 Cache/Buffer to have an additional address latch
      (because the LDSTCompUnit already has it)

    * addr_ok_o (or addr_exc_o) must be waited for.  these will
      be asserted *only* for one cycle and one cycle only.

    * addr_exc_o will be asserted if there is no chance that the
      memory request may be fulfilled.

      busy_o is deasserted on the same cycle as addr_exc_o is asserted.

    * conversely: addr_ok_o must *ONLY* be asserted if there is a
      HUNDRED PERCENT guarantee that the memory request will be
      fulfilled.

    * for a LD, ld.ok will be asserted - for only one clock cycle -
      at any point in the future that is acceptable to the underlying
      Memory subsystem.  the recipient MUST latch ld.data on that cycle.

      busy_o is deasserted on the same cycle as ld.ok is asserted.

    * for a ST, st.ok may be asserted only after addr_ok_o had been
      asserted, alongside valid st.data at the same time.  st.ok
      must only be asserted for one cycle.

      the underlying Memory is REQUIRED to pick up that data and
      guarantee its delivery.  no back-acknowledgement is required.

      busy_o is deasserted on the cycle AFTER st.ok is asserted.
    """

    def __init__(self, name=None, regwid=64, addrwid=48):

        self._regwid = regwid
        self._addrwid = addrwid

        RecordObject.__init__(self, name=name)

        # distinguish op type (ld/st)
        self.is_ld_i = Signal(reset_less=True)
        self.is_st_i = Signal(reset_less=True)

        # LD/ST data length (TODO: other things may be needed)
        self.data_len = Signal(4, reset_less=True)

        # common signals
        self.busy_o = Signal(reset_less=True)     # do not use if busy
        self.go_die_i = Signal(reset_less=True)   # back to reset
        self.addr = Data(addrwid, "addr_i")            # addr/addr-ok
        # addr is valid (TLB, L1 etc.)
        self.addr_ok_o = Signal(reset_less=True)
        self.addr_exc_o = Signal(reset_less=True)  # TODO, "type" of exception

        # LD/ST
        self.ld = Data(regwid, "ld_data_o")  # ok to be set by L0 Cache/Buf
        self.st = Data(regwid, "st_data_i")  # ok to be set by CompUnit


class LDSTPort(Elaboratable):
    def __init__(self, idx, regwid=64, addrwid=48):
        self.pi = PortInterface("ldst_port%d" % idx, regwid, addrwid)

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        # latches
        m.submodules.busy_l = busy_l = SRLatch(False, name="busy")
        m.submodules.cyc_l = cyc_l = SRLatch(True, name="cyc")
        comb += cyc_l.s.eq(0)
        comb += cyc_l.r.eq(0)

        # this is a little weird: we let the L0Cache/Buffer set
        # the outputs: this module just monitors "state".

        # LD/ST requested activates "busy"
        with m.If(self.pi.is_ld_i | self.pi.is_st_i):
            comb += busy_l.s.eq(1)

        # monitor for an exception or the completion of LD.
        with m.If(self.pi.addr_exc_o):
            comb += busy_l.r.eq(1)

        # however ST needs one cycle before busy is reset
        with m.If(self.pi.st.ok | self.pi.ld.ok):
            comb += cyc_l.s.eq(1)

        with m.If(cyc_l.q):
            comb += cyc_l.r.eq(1)
            comb += busy_l.r.eq(1)

        # busy latch outputs to interface
        comb += self.pi.busy_o.eq(busy_l.q)

        return m

    def connect_port(self, inport):
        print ("connect_port", self.pi, inport)
        return [self.pi.is_ld_i.eq(inport.is_ld_i),
                self.pi.is_st_i.eq(inport.is_st_i),
                self.pi.data_len.eq(inport.data_len),
                self.pi.go_die_i.eq(inport.go_die_i),
                self.pi.addr.data.eq(inport.addr.data),
                self.pi.addr.ok.eq(inport.addr.ok),
                self.pi.st.eq(inport.st),
                inport.ld.eq(self.pi.ld),
                inport.busy_o.eq(self.pi.busy_o),
                inport.addr_ok_o.eq(self.pi.addr_ok_o),
                inport.addr_exc_o.eq(self.pi.addr_exc_o),
                ]

    def __iter__(self):
        yield self.pi.is_ld_i
        yield self.pi.is_st_i
        yield from self.pi.data_len
        yield self.pi.busy_o
        yield self.pi.go_die_i
        yield from self.pi.addr.ports()
        yield self.pi.addr_ok_o
        yield self.pi.addr_exc_o

        yield from self.pi.ld.ports()
        yield from self.pi.st.ports()

    def ports(self):
        return list(self)


class TestMemoryPortInterface(Elaboratable):
    """TestMemoryPortInterface

    This is a test class for simple verification of the LDSTCompUnit
    and for the simple core, to be able to run unit tests rapidly and
    with less other code in the way.

    Versions of this which are *compatible* (conform with PortInterface)
    will include augmented-Wishbone Bus versions, including ones that
    connect to L1, L2, MMU etc. etc. however this is the "base lowest
    possible version that complies with PortInterface".
    """

    def __init__(self, regwid=64, addrwid=4):
        # hard-code memory addressing width to 6 bits
        self.mem = TestMemory(regwid, 5, granularity=regwid//8,
                              init=False)
        self.regwid = regwid
        self.addrwid = addrwid
        self.pi = LDSTPort(0, regwid, addrwid)

    @property
    def addrbits(self):
        return log2_int(self.mem.regwid//8)

    def splitaddr(self, addr):
        """split the address into top and bottom bits of the memory granularity
        """
        return addr[:self.addrbits], addr[self.addrbits:]

    def connect_port(self, inport):
        return self.pi.connect_port(inport)

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        # add TestMemory as submodule
        m.submodules.mem = self.mem

        # connect the ports as modules
        m.submodules.port0 = self.pi

        # state-machine latches
        m.submodules.st_active = st_active = SRLatch(False, name="st_active")
        m.submodules.ld_active = ld_active = SRLatch(False, name="ld_active")
        m.submodules.reset_l = reset_l = SRLatch(True, name="reset")
        m.submodules.adrok_l = adrok_l = SRLatch(False, name="addr_acked")

        # expand ld/st binary length/addr[:3] into unary bitmap
        m.submodules.lenexp = lenexp = LenExpand(4, 8)

        lds = Signal(reset_less=True)
        sts = Signal(reset_less=True)
        pi = self.pi.pi
        comb += lds.eq(pi.is_ld_i & pi.busy_o)  # ld-req signals
        comb += sts.eq(pi.is_st_i & pi.busy_o)  # st-req signals

        # convenience variables to reference the "picked" port
        ldport = pi
        stport = pi
        # and the memory ports
        rdport = self.mem.rdport
        wrport = self.mem.wrport

        # Priority-Pickers pick one and only one request, capture its index.
        # from that point on this code *only* "listens" to that port.

        sync += adrok_l.s.eq(0)
        comb += adrok_l.r.eq(0)
        with m.If(lds):
            comb += ld_active.s.eq(1)  # activate LD mode
        with m.Elif(sts):
            comb += st_active.s.eq(1)  # activate ST mode

        # from this point onwards, with the port "picked", it stays picked
        # until ld_active (or st_active) are de-asserted.

        # if now in "LD" mode: wait for addr_ok, then send the address out
        # to memory, acknowledge address, and send out LD data
        with m.If(ld_active.q):
            # set up LenExpander with the LD len and lower bits of addr
            lsbaddr, msbaddr = self.splitaddr(ldport.addr.data)
            comb += lenexp.len_i.eq(ldport.data_len)
            comb += lenexp.addr_i.eq(lsbaddr)
            with m.If(ldport.addr.ok & adrok_l.qn):
                comb += rdport.addr.eq(msbaddr) # addr ok, send thru
                comb += ldport.addr_ok_o.eq(1)  # acknowledge addr ok
                sync += adrok_l.s.eq(1)       # and pull "ack" latch

        # if now in "ST" mode: likewise do the same but with "ST"
        # to memory, acknowledge address, and send out LD data
        with m.If(st_active.q):
            # set up LenExpander with the ST len and lower bits of addr
            lsbaddr, msbaddr = self.splitaddr(stport.addr.data)
            comb += lenexp.len_i.eq(stport.data_len)
            comb += lenexp.addr_i.eq(lsbaddr)
            with m.If(stport.addr.ok):
                comb += wrport.addr.eq(msbaddr)  # addr ok, send thru
                with m.If(adrok_l.qn):
                    comb += stport.addr_ok_o.eq(1)  # acknowledge addr ok
                    sync += adrok_l.s.eq(1)       # and pull "ack" latch

        # NOTE: in both these, below, the port itself takes care
        # of de-asserting its "busy_o" signal, based on either ld.ok going
        # high (by us, here) or by st.ok going high (by the LDSTCompUnit).

        # for LD mode, when addr has been "ok'd", assume that (because this
        # is a "Memory" test-class) the memory read data is valid.
        comb += reset_l.s.eq(0)
        comb += reset_l.r.eq(0)
        with m.If(ld_active.q & adrok_l.q):
            # shift data down before pushing out.  requires masking
            # from the *byte*-expanded version of LenExpand output
            lddata = Signal(self.regwid, reset_less=True)
            # TODO: replace rdport.data with LoadStoreUnitInterface.x_load_data
            # and also handle the ready/stall/busy protocol
            comb += lddata.eq((rdport.data & lenexp.rexp_o) >>
                              (lenexp.addr_i*8))
            comb += ldport.ld.data.eq(lddata)  # put data out
            comb += ldport.ld.ok.eq(1)           # indicate data valid
            comb += reset_l.s.eq(1)   # reset mode after 1 cycle

        # for ST mode, when addr has been "ok'd", wait for incoming "ST ok"
        with m.If(st_active.q & stport.st.ok):
            # shift data up before storing.  lenexp *bit* version of mask is
            # passed straight through as byte-level "write-enable" lines.
            stdata = Signal(self.regwid, reset_less=True)
            comb += stdata.eq(stport.st.data << (lenexp.addr_i*8))
            # TODO: replace with link to LoadStoreUnitInterface.x_store_data
            # and also handle the ready/stall/busy protocol
            comb += wrport.data.eq(stdata)  # write st to mem
            comb += wrport.en.eq(lenexp.lexp_o) # enable writes
            comb += reset_l.s.eq(1)   # reset mode after 1 cycle

        # ugly hack, due to simultaneous addr req-go acknowledge
        reset_delay = Signal(reset_less=True)
        sync += reset_delay.eq(reset_l.q)
        with m.If(reset_delay):
            comb += adrok_l.r.eq(1)     # address reset

        # after waiting one cycle (reset_l is "sync" mode), reset the port
        with m.If(reset_l.q):
            comb += ld_active.r.eq(1)   # leave the ST active for 1 cycle
            comb += st_active.r.eq(1)   # leave the ST active for 1 cycle
            comb += reset_l.r.eq(1)     # clear reset
            comb += adrok_l.r.eq(1)     # address reset

        return m

    def ports(self):
        for p in self.dports:
            yield from p.ports()


def wait_busy(port, no=False):
    while True:
        busy = yield port.pi.busy_o
        print("busy", no, busy)
        if bool(busy) == no:
            break
        yield


def wait_addr(port):
    while True:
        addr_ok = yield port.pi.addr_ok_o
        print("addrok", addr_ok)
        if not addr_ok:
            break
        yield


def wait_ldok(port):
    while True:
        ldok = yield port.pi.ld.ok
        print("ldok", ldok)
        if ldok:
            break
        yield


def l0_cache_st(dut, addr, data, datalen):
    mem = dut.mem
    port1 = dut.pi

    # have to wait until not busy
    yield from wait_busy(port1, no=False)    # wait until not busy

    # set up a ST on the port.  address first:
    yield port1.pi.is_st_i.eq(1)  # indicate ST
    yield port1.pi.data_len.eq(datalen)  # ST length (1/2/4/8)

    yield port1.pi.addr.data.eq(addr)  # set address
    yield port1.pi.addr.ok.eq(1)  # set ok
    yield from wait_addr(port1)             # wait until addr ok
    # yield # not needed, just for checking
    # yield # not needed, just for checking
    # assert "ST" for one cycle (required by the API)
    yield port1.pi.st.data.eq(data)
    yield port1.pi.st.ok.eq(1)
    yield
    yield port1.pi.st.ok.eq(0)

    # can go straight to reset.
    yield port1.pi.is_st_i.eq(0)  # end
    yield port1.pi.addr.ok.eq(0)  # set !ok
    # yield from wait_busy(port1, False)    # wait until not busy


def l0_cache_ld(dut, addr, datalen, expected):

    mem = dut.mem
    port1 = dut.pi

    # have to wait until not busy
    yield from wait_busy(port1, no=False)    # wait until not busy

    # set up a LD on the port.  address first:
    yield port1.pi.is_ld_i.eq(1)  # indicate LD
    yield port1.pi.data_len.eq(datalen)  # LD length (1/2/4/8)

    yield port1.pi.addr.data.eq(addr)  # set address
    yield port1.pi.addr.ok.eq(1)  # set ok
    yield from wait_addr(port1)             # wait until addr ok

    yield from wait_ldok(port1)             # wait until ld ok
    data = yield port1.pi.ld.data

    # cleanup
    yield port1.pi.is_ld_i.eq(0)  # end
    yield port1.pi.addr.ok.eq(0)  # set !ok
    # yield from wait_busy(port1, no=False)    # wait until not busy

    return data


def l0_cache_ldst(arg, dut):
    yield
    addr = 0x2
    data = 0xbeef
    data2 = 0xf00f
    #data = 0x4
    yield from l0_cache_st(dut, 0x2, data, 2)
    yield from l0_cache_st(dut, 0x4, data2, 2)
    result = yield from l0_cache_ld(dut, 0x2, 2, data)
    result2 = yield from l0_cache_ld(dut, 0x4, 2, data2)
    yield
    arg.assertEqual(data, result, "data %x != %x" % (result, data))
    arg.assertEqual(data2, result2, "data2 %x != %x" % (result2, data2))



class TestPIMem(unittest.TestCase):

    def test_pi_mem(self):

        dut = TestMemoryPortInterface(regwid=64)
        #vl = rtlil.convert(dut, ports=dut.ports())
        #with open("test_basic_l0_cache.il", "w") as f:
        #    f.write(vl)

        run_simulation(dut, l0_cache_ldst(self, dut),
                       vcd_name='test_pi_mem_basic.vcd')


if __name__ == '__main__':
    unittest.main(exit=False)

