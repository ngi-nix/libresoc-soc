from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable
from nmutil.latch import SRLatch


class DepCell(Elaboratable):
    """ FU Dependency Cell
    """
    def __init__(self, llen=1):
        self.llen = llen
        # inputs
        self.pend_i = Signal(llen, reset_less=True)    # pending bit in (left)
        self.issue_i = Signal(llen, reset_less=True)   # Issue in (top)
        self.go_i = Signal(llen, reset_less=True)      # Go read/write in (left)
        self.die_i = Signal(llen, reset_less=True)     # Go die in (left)

        # wait
        self.wait_o = Signal(llen, reset_less=True)  # wait out (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.l = l = SRLatch(sync=False, llen=self.llen) # async latch

        # reset on go HI, set on dest and issue
        m.d.comb += l.s.eq(self.issue_i & self.pend_i)
        m.d.comb += l.r.eq(self.go_i | self.die_i)

        # wait out
        m.d.comb += self.wait_o.eq(l.qlq & ~self.issue_i)

        return m

    def __iter__(self):
        yield self.pend_i
        yield self.issue_i
        yield self.go_i
        yield self.die_i
        yield self.wait_o

    def ports(self):
        return list(self)


class FUDependenceCell(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
    """
    def __init__(self, n_fu=1):
        self.n_fu = n_fu
        # inputs
        self.rd_pend_i = Signal(n_fu, reset_less=True) # read pend in (left)
        self.wr_pend_i = Signal(n_fu, reset_less=True) # write pend in (left)
        self.issue_i = Signal(n_fu, reset_less=True)    # Issue in (top)

        self.go_wr_i = Signal(n_fu, reset_less=True) # Go Write in (left)
        self.go_rd_i = Signal(n_fu, reset_less=True)  # Go Read in (left)
        self.go_die_i = Signal(n_fu, reset_less=True) # Go Die in (left)

        # outputs (latched rd/wr wait)
        self.rd_wait_o = Signal(n_fu, reset_less=True) # read wait out (right)
        self.wr_wait_o = Signal(n_fu, reset_less=True) # write wait out (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.rd_c = rd_c = DepCell(self.n_fu)
        m.submodules.wr_c = wr_c = DepCell(self.n_fu)

        # connect issue
        for c in [rd_c, wr_c]:
            m.d.comb += c.issue_i.eq(self.issue_i)
            m.d.comb += c.die_i.eq(self.go_die_i)

        # connect go_rd / go_wr 
        m.d.comb += wr_c.go_i.eq(self.go_wr_i)
        m.d.comb += rd_c.go_i.eq(self.go_rd_i)

        # connect pend_i
        m.d.comb += wr_c.pend_i.eq(self.wr_pend_i)
        m.d.comb += rd_c.pend_i.eq(self.rd_pend_i)

        # connect output
        m.d.comb += self.wr_wait_o.eq(wr_c.wait_o)
        m.d.comb += self.rd_wait_o.eq(rd_c.wait_o)

        return m

    def __iter__(self):
        yield self.rd_pend_i
        yield self.wr_pend_i
        yield self.issue_i
        yield self.go_wr_i
        yield self.go_rd_i
        yield self.go_die_i
        yield self.rd_wait_o
        yield self.wr_wait_o
                
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
    yield dut.go_rd_i.eq(1)
    yield
    yield dut.go_rd_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield

def test_dcell():
    dut = FUDependenceCell()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_fu_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
