from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Const, Elaboratable, Array
from nmutil.latch import SRLatch

from functools import reduce
from operator import or_


class FUDependenceCell(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
    """
    def __init__(self, dummy, n_fu, n_src, n_dest):
        self.n_fu = n_fu
        self.n_src = n_src
        self.n_dest = n_dest
        self.dummy = Const(~(1<<dummy), n_fu)
        # inputs
        self.rd_pend_i = Signal(n_fu, reset_less=True) # read pend in (left)
        self.wr_pend_i = Signal(n_fu, reset_less=True) # write pend in (left)
        self.issue_i = Signal(n_fu, reset_less=True)    # Issue in (top)

        # set up go_wr and go_wr array
        rd = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            rd.append(Signal(n_fu, name="gord%d_i" % j, reset_less=True))
        wr = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            wr.append(Signal(n_fu, name="gowr%d_i" % j, reset_less=True))

        self.go_wr_i = Array(wr)  # Go Write in (left)
        self.go_rd_i = Array(rd)  # Go Read in (left)

        self.go_die_i = Signal(n_fu, reset_less=True) # Go Die in (left)

        # outputs (latched rd/wr wait)
        self.rd_wait_o = Signal(n_fu, reset_less=True) # read wait out (right)
        self.wr_wait_o = Signal(n_fu, reset_less=True) # write wait out (right)

    def elaborate(self, platform):
        m = Module()

        # set up rd/wr latches
        rd_c = []
        for i in range(self.n_src):
            rd_l = SRLatch(sync=False, name="rd%d_c" % i, llen=self.n_fu)
            setattr(m.submodules, "src%d_c" % (i+1), rd_l)
            rd_c.append(rd_l)
        wr_c = []
        for i in range(self.n_dest):
            wr_l = SRLatch(sync=False, name="wr%d_c" % i, llen=self.n_fu)
            setattr(m.submodules, "dst%d_c" % (i+1), wr_l)
            wr_c.append(wr_l)

        # reset on go HI, set on dest and issue

        # connect go_wr / pend
        for i in range(self.n_dest):
            m.d.comb += wr_c[i].r.eq(self.go_wr_i[i] | self.go_die_i)
            m.d.comb += wr_c[i].s.eq(self.issue_i & self.wr_pend_i & self.dummy)

        # connect go_rd / pend_i
        for i in range(self.n_src):
            m.d.comb += rd_c[i].r.eq(self.go_rd_i[i] | self.go_die_i)
            m.d.comb += rd_c[i].s.eq(self.issue_i & self.rd_pend_i & self.dummy)

        # connect output with OR-reduce (DO NOT USE bool()!)
        # read-wait (and write-wait) only go off when all GORD (and GOWR) fire
        rd_q = []
        for i in range(self.n_src):
            rd_q.append(rd_c[i].qlq)
        m.d.comb += self.rd_wait_o.eq(reduce(or_, rd_q) & ~self.issue_i)
        wr_q = []
        for i in range(self.n_dest):
            wr_q.append(wr_c[i].qlq)
        m.d.comb += self.wr_wait_o.eq(reduce(or_, wr_q) & ~self.issue_i)

        return m

    def __iter__(self):
        yield self.rd_pend_i
        yield self.wr_pend_i
        yield self.issue_i
        yield from self.go_wr_i
        yield from self.go_rd_i
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
    dut = FUDependenceCell(dummy=4, n_fu=4, n_src=2, n_dest=2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_fu_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
