from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable
from nmutil.latch import SRLatch


class FUDependenceCell(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
    """
    def __init__(self):
        # inputs
        self.rd_pend_i = Signal(reset_less=True)     # read pending in (left)
        self.wr_pend_i = Signal(reset_less=True)     # write pending in (left)
        self.issue_i = Signal(reset_less=True)    # Issue in (top)

        self.go_write_i = Signal(reset_less=True) # Go Write in (left)
        self.go_read_i = Signal(reset_less=True)  # Go Read in (left)

        # outputs (latched rd/wr pend)
        self.rd_pend_o = Signal(reset_less=True)   # read pending out (right)
        self.wr_pend_o = Signal(reset_less=True)   # write pending out (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.rd_l = rd_l = SRLatch()
        m.submodules.wr_l = wr_l = SRLatch()

        # write latch: reset on go_write HI, set on write pending and issue
        m.d.comb += wr_l.s.eq(self.issue_i & self.wr_pend_i)
        m.d.comb += wr_l.r.eq(self.go_write_i)

        # read latch: reset on go_read HI, set on read pending and issue
        m.d.comb += rd_l.s.eq(self.issue_i & self.rd_pend_i)
        m.d.comb += rd_l.r.eq(self.go_read_i)

        # Read/Write Pending Latches (read out horizontally)
        m.d.comb += self.wr_pend_o.eq(wr_l.qn)
        m.d.comb += self.rd_pend_o.eq(rd_l.qn)

        return m

    def __iter__(self):
        yield self.rd_pend_i
        yield self.wr_pend_i
        yield self.issue_i
        yield self.go_write_i
        yield self.go_read_i
        yield self.rd_pend_o
        yield self.wr_pend_o
                
    def ports(self):
        return list(self)


def dcell_sim(dut):
    yield dut.dest_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.src1_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.go_read_i.eq(1)
    yield
    yield dut.go_read_i.eq(0)
    yield
    yield dut.go_write_i.eq(1)
    yield
    yield dut.go_write_i.eq(0)
    yield

def test_dcell():
    dut = FUDependenceCell()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_fu_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
