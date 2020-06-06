"""Group Picker

to select an instruction that is permitted to read (or write)
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
from nmigen import Module, Signal, Elaboratable, Array

#from nmutil.picker import MultiPriorityPicker as MPP
from nmutil.picker import PriorityPicker


class GroupPicker(Elaboratable):
    """ implements 10.5 mitch alsup group picker, p27
    """
    def __init__(self, wid, n_src, n_dst):
        self.n_src, self.n_dst = n_src, n_dst
        self.gp_wid = wid

        # arrays
        rdr = []
        rd = []
        ri = []
        for i in range(n_src):
            rdr.append(Signal(wid, name="rdrel%d_i" % i, reset_less=True))
            rd.append(Signal(wid, name="gord%d_o" % i, reset_less=True))
            ri.append(Signal(wid, name="readable%d_i" % i, reset_less=True))
        wrr = []
        wr = []
        wi = []
        for i in range(n_dst):
            wrr.append(Signal(wid, name="reqrel%d_i" % i, reset_less=True))
            wr.append(Signal(wid, name="gowr%d_o" % i, reset_less=True))
            wi.append(Signal(wid, name="writable%d_i" % i, reset_less=True))

        # inputs
        self.rd_rel_i = Array(rdr)  # go read in (top)
        self.req_rel_i = Array(wrr) # release request in (top)
        self.readable_i = Array(ri) # readable in (top)
        self.writable_i = Array(wi) # writable in (top)

        # outputs
        self.go_rd_o = Array(rd)  # go read (bottom)
        self.go_wr_o = Array(wr)  # go write (bottom)

    def elaborate(self, platform):
        m = Module()

        # combine release (output ready signal) with writeable
        for i in range(self.n_dst):
            wpick = PriorityPicker(self.gp_wid)
            setattr(m.submodules, "wpick%d" % i, wpick)
            m.d.comb += wpick.i.eq(self.writable_i[i] & self.req_rel_i[i])
            m.d.comb += self.go_wr_o[i].eq(wpick.o)

        for i in range(self.n_src):
            rpick = PriorityPicker(self.gp_wid)
            setattr(m.submodules, "rpick%d" % i, rpick)
            m.d.comb += rpick.i.eq(self.readable_i[i] & self.rd_rel_i[i])
            m.d.comb += self.go_rd_o[i].eq(rpick.o)

        return m

    def __iter__(self):
        yield from self.readable_i
        yield from self.writable_i
        yield from self.req_rel_i
        yield from self.rd_rel_i
        yield from self.go_rd_o
        yield from self.go_wr_o

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
    dut = GroupPicker(4, 2, 2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_grp_pick.il", "w") as f:
        f.write(vl)

    run_simulation(dut, grp_pick_sim(dut), vcd_name='test_grp_pick.vcd')

if __name__ == '__main__':
    test_grp_pick()
