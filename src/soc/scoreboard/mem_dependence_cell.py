from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat, Repl
from nmutil.latch import SRLatch


class MemDepRow(Elaboratable):
    """ implements 1st phase Memory Depencency cell
    """
    def __init__(self, n_reg):
        self.n_reg = n_reg
        # inputs
        self.ld_i = Signal(n_reg, reset_less=True)     # Dest in (top)
        self.st_i = Signal(n_reg, reset_less=True)     # oper1 in (top)
        self.issue_i = Signal(reset_less=True)    # Issue in (top)

        self.st_pend_i = Signal(n_reg, reset_less=True) # Read pend in (top)
        self.ld_pend_i = Signal(n_reg, reset_less=True) # Write pend in (top)
        self.v_st_rsel_o = Signal(n_reg, reset_less=True) # Read pend out (bot)
        self.v_ld_rsel_o = Signal(n_reg, reset_less=True) # Write pend out (bot)

        self.go_ld_i = Signal(reset_less=True) # Go Write in (left)
        self.go_st_i = Signal(reset_less=True)  # Go Read in (left)
        self.go_die_i = Signal(reset_less=True) # Go Die in (left)

        # for Register File Select Lines (vertical)
        self.ld_rsel_o = Signal(n_reg, reset_less=True)  # dest reg sel (bot)
        self.st_rsel_o = Signal(n_reg, reset_less=True)  # src1 reg sel (bot)

        # for Function Unit "forward progress" (horizontal)
        self.ld_fwd_o = Signal(n_reg, reset_less=True)   # dest FU fw (right)
        self.st_fwd_o = Signal(n_reg, reset_less=True)   # src1 FU fw (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.ld_c = ld_c = SRLatch(sync=False, llen=self.n_reg)
        m.submodules.st_c = st_c = SRLatch(sync=False, llen=self.n_reg)

        # connect go_rd / go_wr (dest->wr, src->rd)
        ld_die = Signal(reset_less=True)
        st_die = Signal(reset_less=True)
        m.d.comb += ld_die.eq(self.go_ld_i | self.go_die_i)
        m.d.comb += st_die.eq(self.go_st_i | self.go_die_i)
        m.d.comb += ld_c.r.eq(Repl(ld_die, self.n_reg))
        m.d.comb += st_c.r.eq(Repl(st_die, self.n_reg))

        # connect input reg bit (unary)
        i_ext = Repl(self.issue_i, self.n_reg)
        m.d.comb += ld_c.s.eq(i_ext & self.ld_i)
        m.d.comb += st_c.s.eq(i_ext & self.st_i)

        # connect up hazard checks: read-after-write and write-after-read
        m.d.comb += self.ld_fwd_o.eq(ld_c.q & self.st_pend_i)
        m.d.comb += self.st_fwd_o.eq(st_c.q & self.ld_pend_i)

        # connect reg-sel outputs
        st_ext = Repl(self.go_st_i, self.n_reg)
        ld_ext = Repl(self.go_ld_i, self.n_reg)
        m.d.comb += self.ld_rsel_o.eq(ld_c.qlq & ld_ext)
        m.d.comb += self.st_rsel_o.eq(st_c.qlq & st_ext)

        # to be accumulated to indicate if register is in use (globally)
        # after ORing, is fed back in to st_pend_i / ld_pend_i
        m.d.comb += self.v_st_rsel_o.eq(st_c.qlq)
        m.d.comb += self.v_ld_rsel_o.eq(ld_c.qlq)

        return m

    def __iter__(self):
        yield self.ld_i
        yield self.st_i
        yield self.st_pend_i
        yield self.ld_pend_i
        yield self.issue_i
        yield self.go_ld_i
        yield self.go_st_i
        yield self.go_die_i
        yield self.v_ld_rsel_o
        yield self.v_st_rsel_o
        yield self.ld_rsel_o
        yield self.st_rsel_o
        yield self.ld_fwd_o
        yield self.st_fwd_o

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
    yield
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
    dut = MemDepRow(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_mem_drow.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_mem_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
