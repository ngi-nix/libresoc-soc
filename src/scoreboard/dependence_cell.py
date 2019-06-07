from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat, Repl
from nmutil.latch import SRLatch


class DependencyRow(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
        adjusted to be clock-sync'd on rising edge only.
        mitch design (as does 6600) requires alternating rising/falling clock

        * SET mode: issue_i HI, go_i LO, reg_i HI - register is captured
                                                  - FWD is DISABLED (~issue_i)
                                                  - RSEL DISABLED
        * QRY mode: issue_i LO, go_i LO, haz_i HI - FWD is ASSERTED
                                         reg_i HI - ignored
        * GO mode : issue_i LO, go_i HI           - RSEL is ASSERTED
                                         haz_i HI - FWD still can be ASSERTED

        FWD assertion (hazard protection) therefore still occurs in both
        Query and Go Modes, for this cycle, due to the cq register

        GO mode works for one cycle, again due to the cq register capturing
        the latch output.  Without the cq register, the SR Latch (which is
        asynchronous) would be reset at the exact moment that GO was requested,
        and the RSEL would be garbage.
    """
    def __init__(self, n_reg):
        self.n_reg = n_reg
        # inputs
        self.dest_i = Signal(n_reg, reset_less=True)     # Dest in (top)
        self.src1_i = Signal(n_reg, reset_less=True)     # oper1 in (top)
        self.src2_i = Signal(n_reg, reset_less=True)     # oper2 in (top)
        self.issue_i = Signal(reset_less=True)    # Issue in (top)

        self.rd_pend_i = Signal(n_reg, reset_less=True) # Read pend in (top)
        self.wr_pend_i = Signal(n_reg, reset_less=True) # Write pend in (top)
        self.v_rd_rsel_o = Signal(n_reg, reset_less=True) # Read pend out (bot)
        self.v_wr_rsel_o = Signal(n_reg, reset_less=True) # Write pend out (bot)

        self.go_wr_i = Signal(reset_less=True) # Go Write in (left)
        self.go_rd_i = Signal(reset_less=True)  # Go Read in (left)
        self.go_die_i = Signal(reset_less=True) # Go Die in (left)

        # for Register File Select Lines (vertical)
        self.dest_rsel_o = Signal(n_reg, reset_less=True)  # dest reg sel (bot)
        self.src1_rsel_o = Signal(n_reg, reset_less=True)  # src1 reg sel (bot)
        self.src2_rsel_o = Signal(n_reg, reset_less=True)  # src2 reg sel (bot)

        # for Function Unit "forward progress" (horizontal)
        self.dest_fwd_o = Signal(n_reg, reset_less=True)   # dest FU fw (right)
        self.src1_fwd_o = Signal(n_reg, reset_less=True)   # src1 FU fw (right)
        self.src2_fwd_o = Signal(n_reg, reset_less=True)   # src2 FU fw (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.dest_c = dest_c = SRLatch(sync=False, llen=self.n_reg)
        m.submodules.src1_c = src1_c = SRLatch(sync=False, llen=self.n_reg)
        m.submodules.src2_c = src2_c = SRLatch(sync=False, llen=self.n_reg)

        # connect go_rd / go_wr (dest->wr, src->rd)
        wr_die = Signal(reset_less=True)
        rd_die = Signal(reset_less=True)
        m.d.comb += wr_die.eq(self.go_wr_i | self.go_die_i)
        m.d.comb += rd_die.eq(self.go_rd_i | self.go_die_i)
        m.d.comb += dest_c.r.eq(Repl(wr_die, self.n_reg))
        m.d.comb += src1_c.r.eq(Repl(rd_die, self.n_reg))
        m.d.comb += src2_c.r.eq(Repl(rd_die, self.n_reg))

        # connect input reg bit (unary)
        i_ext = Repl(self.issue_i, self.n_reg)
        m.d.comb += dest_c.s.eq(i_ext & self.dest_i)
        m.d.comb += src1_c.s.eq(i_ext & self.src1_i)
        m.d.comb += src2_c.s.eq(i_ext & self.src2_i)

        # connect up hazard checks: read-after-write and write-after-read
        m.d.comb += self.dest_fwd_o.eq(dest_c.q & self.rd_pend_i)
        m.d.comb += self.src1_fwd_o.eq(src1_c.q & self.wr_pend_i)
        m.d.comb += self.src2_fwd_o.eq(src2_c.q & self.wr_pend_i)

        # connect reg-sel outputs
        rd_ext = Repl(self.go_rd_i, self.n_reg)
        wr_ext = Repl(self.go_wr_i, self.n_reg)
        m.d.comb += self.dest_rsel_o.eq(dest_c.qlq & wr_ext)
        m.d.comb += self.src1_rsel_o.eq(src1_c.qlq & rd_ext)
        m.d.comb += self.src2_rsel_o.eq(src2_c.qlq & rd_ext)

        # to be accumulated to indicate if register is in use (globally)
        # after ORing, is fed back in to rd_pend_i / wr_pend_i
        m.d.comb += self.v_rd_rsel_o.eq(src1_c.qlq | src2_c.qlq)
        m.d.comb += self.v_wr_rsel_o.eq(dest_c.qlq)

        return m

    def __iter__(self):
        yield self.dest_i
        yield self.src1_i
        yield self.src2_i
        yield self.rd_pend_i
        yield self.wr_pend_i
        yield self.issue_i
        yield self.go_wr_i
        yield self.go_rd_i
        yield self.go_die_i
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
    yield dut.go_rd_i.eq(1)
    yield
    yield dut.go_rd_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield

def test_dcell():
    dut = DependencyRow(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_drow.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
