from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Const, Elaboratable
from nmutil.latch import SRLatch


class FUMemDependenceCell(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
    """
    def __init__(self, dummy, n_fu=1):
        self.n_fu = n_fu
        self.dummy = Const(~(1<<dummy), n_fu)
        # inputs
        self.st_pend_i = Signal(n_fu, reset_less=True) # read pend in (left)
        self.ld_pend_i = Signal(n_fu, reset_less=True) # write pend in (left)
        self.issue_i = Signal(n_fu, reset_less=True)    # Issue in (top)

        self.go_ld_i = Signal(n_fu, reset_less=True) # Go Write in (left)
        self.go_st_i = Signal(n_fu, reset_less=True)  # Go Read in (left)
        self.go_die_i = Signal(n_fu, reset_less=True) # Go Die in (left)

        # outputs (latched rd/wr wait)
        self.st_wait_o = Signal(n_fu, reset_less=True) # read wait out (right)
        self.ld_wait_o = Signal(n_fu, reset_less=True) # write wait out (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.st_c = st_c = SRLatch(sync=False, llen=self.n_fu)
        m.submodules.ld_c = ld_c = SRLatch(sync=False, llen=self.n_fu)

        # reset on go HI, set on dest and issue
        m.d.comb += st_c.s.eq(self.issue_i & self.st_pend_i)
        m.d.comb += ld_c.s.eq(self.issue_i & self.ld_pend_i)

        # connect go_rd / go_wr 
        m.d.comb += ld_c.r.eq(self.go_ld_i | self.go_die_i)
        m.d.comb += st_c.r.eq(self.go_st_i | self.go_die_i)

        # connect pend_i
        m.d.comb += st_c.s.eq(self.issue_i & self.st_pend_i & self.dummy)
        m.d.comb += ld_c.s.eq(self.issue_i & self.ld_pend_i & self.dummy)

        # connect output
        m.d.comb += self.st_wait_o.eq(st_c.qlq & ~self.issue_i)
        m.d.comb += self.ld_wait_o.eq(ld_c.qlq & ~self.issue_i)

        return m

    def __iter__(self):
        yield self.st_pend_i
        yield self.ld_pend_i
        yield self.issue_i
        yield self.go_ld_i
        yield self.go_st_i
        yield self.go_die_i
        yield self.st_wait_o
        yield self.ld_wait_o
                
    def ports(self):
        return list(self)


def dcell_sim(dut):
    yield dut.ld_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.st_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.go_st_i.eq(1)
    yield
    yield dut.go_st_i.eq(0)
    yield
    yield dut.go_ld_i.eq(1)
    yield
    yield dut.go_ld_i.eq(0)
    yield

def test_dcell():
    dut = FUMemDependenceCell(dummy=0, n_fu=4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fumem_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_fumem_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
