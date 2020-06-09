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

from soc.experiment.compldst import CompLDSTOpSubset
from soc.decoder.power_decoder2 import Data
#from nmutil.picker import PriorityPicker
from nmigen.lib.coding import PriorityEncoder
from soc.scoreboard.addr_split import LDSTSplitter
from soc.scoreboard.addr_match import LenExpand

# for testing purposes
from soc.experiment.testmem import TestMemory


class PortInterface(RecordObject):
    """PortInterface

    defines the interface - the API - that the LDSTCompUnit connects
    to.  note that this is NOT a "fire-and-forget" interface.  the
    LDSTCompUnit *must* be kept appraised that the request is in
    progress, and only when it has a 100% successful completion rate
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
        self.op = CompLDSTOpSubset()  # hm insn_type ld/st duplicates here

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

# TODO: elaborate function


class DualPortSplitter(Elaboratable):
    """DualPortSplitter

    * one incoming PortInterface
    * two *OUTGOING* PortInterfaces
    * uses LDSTSplitter to do it

    (actually, thinking about it LDSTSplitter could simply be
     modified to conform to PortInterface: one in, two out)

    once that is done each pair of ports may be wired directly
    to the dual ports of L0CacheBuffer

    The split is carried out so that, regardless of alignment or
    mis-alignment, outgoing PortInterface[0] takes bit 4 == 0
    of the address, whilst outgoing PortInterface[1] takes
    bit 4 == 1.

    PortInterface *may* need to be changed so that the length is
    a binary number (accepting values 1-16).
    """
    def __init__(self):
        self.outp = [PortInterface(name="outp_0"),
                     PortInterface(name="outp_1")]
        self.inp  = PortInterface(name="inp")
        print(self.outp)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.splitter = splitter = LDSTSplitter(64, 48, 4)
        comb += splitter.addr_i.eq(self.inp.addr) #XXX
        #comb += splitter.len_i.eq()
        #comb += splitter.valid_i.eq()
        comb += splitter.is_ld_i.eq(self.inp.is_ld_i)
        comb += splitter.is_st_i.eq(self.inp.is_st_i)
        #comb += splitter.st_data_i.eq()
        #comb += splitter.sld_valid_i.eq()
        #comb += splitter.sld_data_i.eq()
        #comb += splitter.sst_valid_i.eq()
        return m

class DataMergerRecord(Record):
    """
    {data: 128 bit, byte_enable: 16 bit}
    """

    def __init__(self, name=None):
        layout = (('data', 128),
                  ('en', 16)
                  )

        Record.__init__(self, Layout(layout), name=name)

        #FIXME: make resetless

# TODO: formal verification

class DataMerger(Elaboratable):
    """DataMerger

    Merges data based on an address-match matrix.
    Identifies (picks) one (any) row, then uses that row,
    based on matching address bits, to merge (OR) all data
    rows into the output.

    Basically, by the time DataMerger is used, all of its incoming data is
    determined not to conflict.  The last step before actually submitting
    the request to the Memory Subsystem is to work out which requests,
    on the same 128-bit cache line, can be "merged" due to them being:
    (A) on the same address (bits 4 and above) (B) having byte-enable
    lines that (as previously mentioned) do not conflict.

    Therefore, put simply, this module will:
    (1) pick a row (any row) and identify it by an index labelled "idx"
    (2) merge all byte-enable lines which are on that same address, as
        indicated by addr_match_i[idx], onto the output
    """

    def __init__(self, array_size):
        """
        :addr_array_i: an NxN Array of Signals with bits set indicating address
                       match.  bits across the diagonal (addr_array_i[x][x])
                       will always be set, to indicate "active".
        :data_i: an Nx Array of Records {data: 128 bit, byte_enable: 16 bit}
        :data_o: an Output Record of same type
                 {data: 128 bit, byte_enable: 16 bit}
        """
        self.array_size = array_size
        ul = []
        for i in range(array_size):
            ul.append(Signal(array_size,
                             reset_less=True,
                             name="addr_match_%d" % i))
        self.addr_array_i = Array(ul)

        ul = []
        for i in range(array_size):
            ul.append(DataMergerRecord())
        self.data_i = Array(ul)
        self.data_o = DataMergerRecord()

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        #(1) pick a row
        m.submodules.pick = pick = PriorityEncoder(self.array_size)
        for j in range(self.array_size):
            comb += pick.i[j].eq(self.addr_array_i[j].bool())
        valid = ~pick.n
        idx = pick.o
        #(2) merge
        with m.If(valid):
            l = []
            for j in range(self.array_size):
                select = self.addr_array_i[idx][j]
                r = DataMergerRecord()
                with m.If(select):
                    comb += r.eq(self.data_i[j])
                l.append(r)
            comb += self.data_o.data.eq(ortreereduce(l,"data"))
            comb += self.data_o.en.eq(ortreereduce(l,"en"))

        return m


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

    def __iter__(self):
        yield self.pi.is_ld_i
        yield self.pi.is_st_i
        yield from self.pi.op.ports()
        yield self.pi.busy_o
        yield self.pi.go_die_i
        yield from self.pi.addr.ports()
        yield self.pi.addr_ok_o
        yield self.pi.addr_exc_o

        yield from self.pi.ld.ports()
        yield from self.pi.st.ports()

    def ports(self):
        return list(self)


class L0CacheBuffer(Elaboratable):
    """L0 Cache / Buffer

    Note that the final version will have *two* interfaces per LDSTCompUnit,
    to cover mis-aligned requests, as well as *two* 128-bit L1 Cache
    interfaces: one for odd (addr[4] == 1) and one for even (addr[4] == 1).

    This version is to be used for test purposes (and actively maintained
    for such, rather than "replaced")

    There are much better ways to implement this.  However it's only
    a "demo" / "test" class, and one important aspect: it responds
    combinatorially, where a nmigen FSM's state-changes only activate
    on clock-sync boundaries.
    """

    def __init__(self, n_units, mem, regwid=64, addrwid=48):
        self.n_units = n_units
        self.mem = mem
        self.regwid = regwid
        self.addrwid = addrwid
        ul = []
        for i in range(n_units):
            ul.append(LDSTPort(i, regwid, addrwid))
        self.dports = Array(ul)

    @property
    def addrbits(self):
        return log2_int(self.mem.regwid//8)

    def splitaddr(self, addr):
        """split the address into top and bottom bits of the memory granularity
        """
        return addr[:self.addrbits], addr[self.addrbits:]

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        # connect the ports as modules
        for i in range(self.n_units):
            setattr(m.submodules, "port%d" % i, self.dports[i])

        # state-machine latches
        m.submodules.st_active = st_active = SRLatch(False, name="st_active")
        m.submodules.ld_active = ld_active = SRLatch(False, name="ld_active")
        m.submodules.reset_l = reset_l = SRLatch(True, name="reset")
        m.submodules.idx_l = idx_l = SRLatch(False, name="idx_l")
        m.submodules.adrok_l = adrok_l = SRLatch(False, name="addr_acked")

        # find one LD (or ST) and do it.  only one per cycle.
        # TODO: in the "live" (production) L0Cache/Buffer, merge multiple
        # LD/STs using mask-expansion - see LenExpand class

        m.submodules.ldpick = ldpick = PriorityEncoder(self.n_units)
        m.submodules.stpick = stpick = PriorityEncoder(self.n_units)
        m.submodules.lenexp = lenexp = LenExpand(self.regwid//8, 8)

        lds = Signal(self.n_units, reset_less=True)
        sts = Signal(self.n_units, reset_less=True)
        ldi = []
        sti = []
        for i in range(self.n_units):
            pi = self.dports[i].pi
            ldi.append(pi.is_ld_i & pi.busy_o)  # accumulate ld-req signals
            sti.append(pi.is_st_i & pi.busy_o)  # accumulate st-req signals
        # put the requests into the priority-pickers
        comb += ldpick.i.eq(Cat(*ldi))
        comb += stpick.i.eq(Cat(*sti))

        # hmm, have to select (record) the right port index
        nbits = log2_int(self.n_units, False)
        ld_idx = Signal(nbits, reset_less=False)
        st_idx = Signal(nbits, reset_less=False)
        # use these because of the sync-and-comb pass-through capability
        latchregister(m, ldpick.o, ld_idx, idx_l.qn, name="ld_idx_l")
        latchregister(m, stpick.o, st_idx, idx_l.qn, name="st_idx_l")

        # convenience variables to reference the "picked" port
        ldport = self.dports[ld_idx].pi
        stport = self.dports[st_idx].pi
        # and the memory ports
        rdport = self.mem.rdport
        wrport = self.mem.wrport

        # Priority-Pickers pick one and only one request, capture its index.
        # from that point on this code *only* "listens" to that port.

        sync += adrok_l.s.eq(0)
        comb += adrok_l.r.eq(0)
        with m.If(~ldpick.n):
            comb += ld_active.s.eq(1)  # activate LD mode
            comb += idx_l.r.eq(1)  # pick (and capture) the port index
        with m.Elif(~stpick.n):
            comb += st_active.s.eq(1)  # activate ST mode
            comb += idx_l.r.eq(1)  # pick (and capture) the port index

        # from this point onwards, with the port "picked", it stays picked
        # until ld_active (or st_active) are de-asserted.

        # if now in "LD" mode: wait for addr_ok, then send the address out
        # to memory, acknowledge address, and send out LD data
        with m.If(ld_active.q):
            with m.If(ldport.addr.ok & adrok_l.qn):
                comb += rdport.addr.eq(ldport.addr.data)  # addr ok, send thru
                comb += ldport.addr_ok_o.eq(1)  # acknowledge addr ok
                sync += adrok_l.s.eq(1)       # and pull "ack" latch

        # if now in "ST" mode: likewise do the same but with "ST"
        # to memory, acknowledge address, and send out LD data
        with m.If(st_active.q):
            with m.If(stport.addr.ok):
                comb += wrport.addr.eq(stport.addr.data)  # addr ok, send thru
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
            comb += ldport.ld.data.eq(rdport.data)  # put data out
            comb += ldport.ld.ok.eq(1)             # indicate data valid
            comb += reset_l.s.eq(1)   # reset mode after 1 cycle

        # for ST mode, when addr has been "ok'd", wait for incoming "ST ok"
        with m.If(st_active.q & stport.st.ok):
            comb += wrport.data.eq(stport.st.data)  # write st to mem
            comb += wrport.en.eq(1)                # enable write
            comb += reset_l.s.eq(1)   # reset mode after 1 cycle

        # after waiting one cycle (reset_l is "sync" mode), reset the port
        with m.If(reset_l.q):
            comb += idx_l.s.eq(1)  # deactivate port-index selector
            comb += ld_active.r.eq(1)   # leave the ST active for 1 cycle
            comb += st_active.r.eq(1)   # leave the ST active for 1 cycle
            comb += reset_l.r.eq(1)     # clear reset
            comb += adrok_l.r.eq(1)     # address reset

        return m

    def ports(self):
        for p in self.dports:
            yield from p.ports()


class TstL0CacheBuffer(Elaboratable):
    def __init__(self, n_units=3, regwid=16, addrwid=4):
        self.mem = TestMemory(regwid, addrwid)
        self.l0 = L0CacheBuffer(n_units, self.mem, regwid, addrwid)

    def elaborate(self, platform):
        m = Module()
        m.submodules.mem = self.mem
        m.submodules.l0 = self.l0

        return m

    def ports(self):
        yield from self.l0.ports()
        yield self.mem.rdport.addr
        yield self.mem.rdport.data
        yield self.mem.wrport.addr
        yield self.mem.wrport.data
        # TODO: mem ports


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


def l0_cache_st(dut, addr, data):
    l0 = dut.l0
    mem = dut.mem
    port0 = l0.dports[0]
    port1 = l0.dports[1]

    # have to wait until not busy
    yield from wait_busy(port1, no=False)    # wait until not busy

    # set up a ST on the port.  address first:
    yield port1.pi.is_st_i.eq(1)  # indicate LD

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


def l0_cache_ld(dut, addr, expected):

    l0 = dut.l0
    mem = dut.mem
    port0 = l0.dports[0]
    port1 = l0.dports[1]

    # have to wait until not busy
    yield from wait_busy(port1, no=False)    # wait until not busy

    # set up a LD on the port.  address first:
    yield port1.pi.is_ld_i.eq(1)  # indicate LD

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


def l0_cache_ldst(dut):
    yield
    addr = 0x2
    data = 0xbeef
    data2 = 0xf00f
    #data = 0x4
    yield from l0_cache_st(dut, 0x2, data)
    yield from l0_cache_st(dut, 0x3, data2)
    result = yield from l0_cache_ld(dut, 0x2, data)
    result2 = yield from l0_cache_ld(dut, 0x3, data2)
    yield
    assert data == result, "data %x != %x" % (result, data)
    assert data2 == result2, "data2 %x != %x" % (result2, data2)

def data_merger_merge(dut):
    print("data_merger")
    #starting with all inputs zero
    yield Settle()
    en = yield dut.data_o.en
    data = yield dut.data_o.data
    assert en == 0, "en must be zero"
    assert data == 0, "data must be zero"
    yield

    yield dut.addr_array_i[0].eq(0xFF)
    for j in range(dut.array_size):
        yield dut.data_i[j].en.eq(1 << j)
        yield dut.data_i[j].data.eq(0xFF << (16*j))
    yield Settle()

    en = yield dut.data_o.en
    data = yield dut.data_o.data
    assert data == 0xff00ff00ff00ff00ff00ff00ff00ff
    assert en == 0xff
    yield

def test_l0_cache():

    dut = TstL0CacheBuffer(regwid=64)
    #vl = rtlil.convert(dut, ports=dut.ports())
    #with open("test_basic_l0_cache.il", "w") as f:
    #    f.write(vl)

    run_simulation(dut, l0_cache_ldst(dut),
                   vcd_name='test_l0_cache_basic.vcd')

def test_data_merger():

    dut = DataMerger(8)
    #vl = rtlil.convert(dut, ports=dut.ports())
    #with open("test_data_merger.il", "w") as f:
    #    f.write(vl)

    run_simulation(dut, data_merger_merge(dut),
                   vcd_name='test_data_merger.vcd')

def test_dual_port_splitter():

    dut = DualPortSplitter()
    #vl = rtlil.convert(dut, ports=dut.ports())
    #with open("test_data_merger.il", "w") as f:
    #    f.write(vl)

    #run_simulation(dut, data_merger_merge(dut),
    #               vcd_name='test_dual_port_splitter.vcd')

if __name__ == '__main__':
    test_l0_cache()
    test_data_merger()
    #test_dual_port_splitter()
