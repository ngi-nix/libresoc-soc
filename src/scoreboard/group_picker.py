""" Group Picker: to select an instruction that is permitted to read (or write)
    based on the Function Unit expressing a *desire* to read (or write).

    The job of the Group Picker is extremely simple yet extremely important.
    It sits in front of a register file port (read or write) and stops it from
    being corrupted.  It's a "port contention selector", basically.

    The way it works is:

    * Function Units need to read from (or write to) the register file,
      in order to get (or store) their operands, so they each have a signal,
      readable (or writable), which "expresses" this need.  This is an
      *unary* encoding.

    * The Function Units also have a signal which indicates that they
      are requesting "release" of the register file port (this because
      in the scoreboard, readable/writable can be permanently HI even
      if the FU is idle, whereas the "release" signal is very specifically
      only HI if the read (or write) latch is still active)

    * The Group Picker takes this unary encoding of the desire to read
      (or write) and, on a priority basis, activates one *and only* one
      of those signals, again as an unary output.

    * Due to the way that the Computation Unit works, that signal (Go_Read
      or Go_Write) will fire for one (and only one) cycle, and can be used
      to enable the register file port read (or write) lines.  The Go_Read/Wr
      signal basically loops back to the Computation Unit and resets the
      "desire-to-read/write-expressing" latch.

    In theory (and in practice!) the following is possible:

    * Separate src1 and src2 Group Pickers.  This would allow instructions
      with only one operand to read to not block up other instructions,
      and it would also allow 3-operand instructions to be interleaved
      with 1 and 2 operand instructions.

    * *Multiple* Group Pickers (multi-issue).  This would require
      a corresponding increase in the number of register file ports,
      either 4R2W (or more) or by "striping" the register file into
      split banks (a strategy best deployed on Vector Processors)

"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable

from nmutil.picker import PriorityPicker


class GroupPicker(Elaboratable):
    """ implements 10.5 mitch alsup group picker, p27
    """
    def __init__(self, wid):
        self.gp_wid = wid
        # inputs
        self.readable_i = Signal(wid, reset_less=True) # readable in (top)
        self.writable_i = Signal(wid, reset_less=True) # writable in (top)
        self.rd_rel_i = Signal(wid, reset_less=True)   # go read in (top)
        self.req_rel_i = Signal(wid, reset_less=True) # release request in (top)

        # outputs
        self.go_rd_o = Signal(wid, reset_less=True)  # go read (bottom)
        self.go_wr_o = Signal(wid, reset_less=True)  # go write (bottom)

    def elaborate(self, platform):
        m = Module()

        m.submodules.rpick = rpick = PriorityPicker(self.gp_wid)
        m.submodules.wpick = wpick = PriorityPicker(self.gp_wid)

        # combine release (output ready signal) with writeable
        m.d.comb += wpick.i.eq(self.writable_i & self.req_rel_i)
        m.d.comb += self.go_wr_o.eq(wpick.o)

        m.d.comb += rpick.i.eq(self.readable_i & self.rd_rel_i)
        m.d.comb += self.go_rd_o.eq(rpick.o)

        return m

    def __iter__(self):
        yield self.readable_i
        yield self.writable_i
        yield self.req_rel_i
        yield self.go_rd_o
        yield self.go_wr_o

    def ports(self):
        return list(self)


def grp_pick_sim(dut):
    yield dut.dest_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.src1_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.rd_rel_i.eq(1)
    yield
    yield dut.rd_rel_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield

def test_grp_pick():
    dut = GroupPicker(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_grp_pick.il", "w") as f:
        f.write(vl)

    run_simulation(dut, grp_pick_sim(dut), vcd_name='test_grp_pick.vcd')

if __name__ == '__main__':
    test_grp_pick()
