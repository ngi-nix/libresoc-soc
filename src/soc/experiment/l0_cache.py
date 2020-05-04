"""L0 Cache/Buffer

This first version is intended for prototyping and test purposes:
it has "direct" access to Memory.

The intention is that this version remains an integral part of the
test infrastructure, and, just as with minerva's memory arrangement,
a dynamic runtime config *selects* alternative memory arrangements
rather than *replaces and discards* this code.

"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Elaboratable, Array
from nmutil.iocontrol import RecordObject

from nmutil.latch import SRLatch, latchregister
from soc.decoder.power_decoder2 import Data
from soc.decoder.power_enums import InternalOp

from soc.experiment.compldst import CompLDSTOpSubset
from soc.decoder.power_decode2 import Data
from nmutil.picker import PriorityPicker


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

    * addr.ok is to be asserted when the LD/ST address is known
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

      busy_o is deasserted on the same cycle as ld.ok is asserted.
    """

    def __init__(self, name=None):

        RecordObject.__init__(self, name=name)

        # distinguish op type (ld/st)
        self.is_ld_i = Signal(reset_less=True)
        self.is_st_i = Signal(reset_less=True)
        self.op = CompLDSTOpSubset() # hm insn_type ld/st duplicates here

        # common signals
        self.busy_o = Signal(reset_less=True)     # do not use if busy
        self.go_die_i = Signal(reset_less=True)   # back to reset
        self.addr = Data(48, "addr_i")            # addr/addr-ok
        self.addr_ok_o = Signal(reset_less=True)  # addr is valid (TLB, L1 etc.)
        self.addr_exc_o = Signal(reset_less=True) # TODO, "type" of exception

        # LD/ST
        self.ld = Data(64, "ld_data_o") # ok to be set by L0 Cache/Buf
        self.st = Data(64, "st_data_i") # ok to be set by CompUnit


class L0CacheBuffer(Elaboratable):
    """L0 Cache / Buffer

    Note that the final version will have *two* interfaces per LDSTCompUnit,
    to cover mis-aligned requests.  This version is to be used for test
    purposes (and actively maintained for test purposes)

    """

    def __init__(self, n_units, mem):
        self.n_units = n_units
        self.mem = mem
        ul = []
        for i in range(n_units):
            ul.append(PortInterface("ldst_port%d" % i))
        self.ports = Array(ul)

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        # find one LD (or ST) and do it.  only one per cycle.
        # TODO: in the "live" (production) L0Cache/Buffer, merge multiple
        # LD/STs using mask-expansion - see LenExpand class

        m.submodules.ldpick = ldpick = PriorityPicker()
        m.submodules.stpick = stpick = PriorityPicker()

        lds = Signal(self.n_units, reset_less=True)
        sts = Signal(self.n_units, reset_less=True)
        ldi = []
        sti = []
        for i in range(self.n_units):
            ldi.append(self.ports[i].is_ld_i) # accumulate ld-req signals
            sti.append(self.ports[i].is_st_i) # accumulate st-req signals
        # put the requests into the priority-pickers
        comb += ldpick.i.eq(Cat(*ldi))
        comb += stpick.i.eq(Cat(*sti))

        # Priority-Pickers pick one and only one request
        with m.If(ldpick.en_o):
            rdport = self.mem.rdport
            ldd_r = Signal(self.rwid, reset_less=True)  # Dest register
            # latch LD-out
            latchregister(m, rdport.data, ldd_r, ldlatch, "ldo_r")
            sync += ldlatch.eq(self.load_mem_o)
            with m.If(self.load_mem_o):
                comb += rdport.addr.eq(self.addr_o)

        with m.ElIf(stpick.en_o):
            wrport = self.mem.wrport
            comb += wrport.addr.eq(self.addr_o)
            comb += wrport.data.eq(src2_r)
            comb += wrport.en.eq(1)


        return m


def test_l0_cache():
    from alu_hier import ALU

    alu = ALU(16)
    dut = ComputationUnitNoDelay(16, alu)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compalu.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut), vcd_name='test_compalu.vcd')


if __name__ == '__main__':
    test_l0_cache()
