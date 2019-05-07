from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable
from nmutil.latch import SRLatch


class DependenceCell(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
    """
    def __init__(self):
        # inputs
        self.dest_i = Signal(reset_less=True)     # Dest in (top)
        self.src1_i = Signal(reset_less=True)     # oper1 in (top)
        self.src2_i = Signal(reset_less=True)     # oper2 in (top)
        self.issue_i = Signal(reset_less=True)    # Issue in (top)

        self.go_write_i = Signal(reset_less=True) # Go Write in (left)
        self.go_read_i = Signal(reset_less=True)  # Go Read in (left)

        # for Register File Select Lines (vertical)
        self.dest_rsel_o = Signal(reset_less=True)  # dest reg sel (bottom)
        self.src1_rsel_o = Signal(reset_less=True)  # src1 reg sel (bottom)
        self.src2_rsel_o = Signal(reset_less=True)  # src2 reg sel (bottom)

        # for Function Unit "forward progress" (horizontal)
        self.dest_fwd_o = Signal(reset_less=True)   # dest FU fw (right)
        self.src1_fwd_o = Signal(reset_less=True)   # src1 FU fw (right)
        self.src2_fwd_o = Signal(reset_less=True)   # src2 FU fw (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.dest_l = dest_l = SRLatch()
        m.submodules.src1_l = src1_l = SRLatch()
        m.submodules.src2_l = src2_l = SRLatch()

        # destination latch: reset on go_write HI, set on dest and issue
        m.d.comb += dest_l.s.eq(self.issue_i & self.dest_i)
        m.d.comb += dest_l.r.eq(self.go_write_i)

        # src1 latch: reset on go_read HI, set on src1_i and issue
        m.d.comb += src1_l.s.eq(self.issue_i & self.src1_i)
        m.d.comb += src1_l.r.eq(self.go_read_i)

        # src2 latch: reset on go_read HI, set on op2_i and issue
        m.d.comb += src2_l.s.eq(self.issue_i & self.src2_i)
        m.d.comb += src2_l.r.eq(self.go_read_i)

        # FU "Forward Progress" (read out horizontally)
        m.d.comb += self.dest_fwd_o.eq(dest_l.qn & self.dest_i)
        m.d.comb += self.src1_fwd_o.eq(src1_l.qn & self.src1_i)
        m.d.comb += self.src2_fwd_o.eq(src2_l.qn & self.src2_i)

        # Register File Select (read out vertically)
        m.d.comb += self.dest_rsel_o.eq(dest_l.qn & self.go_write_i)
        m.d.comb += self.src1_rsel_o.eq(src1_l.qn & self.go_read_i)
        m.d.comb += self.src2_rsel_o.eq(src2_l.qn & self.go_read_i)

        return m

    def __iter__(self):
        yield self.dest_i
        yield self.src1_i
        yield self.src2_i
        yield self.issue_i
        yield self.go_write_i
        yield self.go_read_i
        yield self.dest_rsel_o
        yield self.src1_rsel_o
        yield self.src2_rsel_o
        yield self.dest_fwd_o
        yield self.src1_fwd_o
        yield self.src2_fwd_o
                
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
    yield
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
    dut = DependenceCell()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
