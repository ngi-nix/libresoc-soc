from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat
from nmutil.latch import SRLatch


class DepCell(Elaboratable):
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
    def __init__(self):
        # inputs
        self.reg_i = Signal(reset_less=True)     # reg bit in (top)
        self.issue_i = Signal(reset_less=True)   # Issue in (top)
        self.hazard_i = Signal(reset_less=True)  # to check hazard
        self.go_i = Signal(reset_less=True)      # Go read/write in (left)
        self.q_o = Signal(reset_less=True)       # Latch out (register active)

        # for Register File Select Lines (vertical)
        self.rsel_o = Signal(reset_less=True)  # reg sel (bottom)
        # for Function Unit "forward progress" (horizontal)
        self.fwd_o = Signal(reset_less=True)   # FU forard progress (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.l = l = SRLatch(sync=False) # async latch

        # record current version of q in a sync'd register
        cq = Signal() # resets to 0
        m.d.sync += cq.eq(l.q)

        # reset on go HI, set on dest and issue
        m.d.comb += l.s.eq(self.issue_i & self.reg_i)
        m.d.comb += l.r.eq(self.go_i)

        # Function Unit "Forward Progress".
        m.d.comb += self.fwd_o.eq((l.q) & self.hazard_i)# & ~self.issue_i)

        # Register Select. Activated on go read/write and *current* latch set
        m.d.comb += self.rsel_o.eq((cq | l.q) & self.go_i)

        m.d.comb += self.q_o.eq(cq | l.q)

        return m

    def __iter__(self):
        yield self.reg_i
        yield self.hazard_i
        yield self.issue_i
        yield self.go_i
        yield self.q_o
        yield self.rsel_o
        yield self.fwd_o

    def ports(self):
        return list(self)


class DependenceCell(Elaboratable):
    """ implements 11.4.7 mitch alsup dependence cell, p27
    """
    def __init__(self):
        # inputs
        self.dest_i = Signal(reset_less=True)     # Dest in (top)
        self.src1_i = Signal(reset_less=True)     # oper1 in (top)
        self.src2_i = Signal(reset_less=True)     # oper2 in (top)
        self.issue_i = Signal(reset_less=True)    # Issue in (top)

        self.rd_pend_i = Signal(reset_less=True) # Read pending in (top)
        self.wr_pend_i = Signal(reset_less=True) # Write pending in (top)
        self.rd_rsel_o = Signal(reset_less=True) # Read pending out (bottom)
        self.wr_rsel_o = Signal(reset_less=True) # Write pending out (bottom)

        self.go_wr_i = Signal(reset_less=True) # Go Write in (left)
        self.go_rd_i = Signal(reset_less=True)  # Go Read in (left)

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
        m.submodules.dest_c = dest_c = DepCell()
        m.submodules.src1_c = src1_c = DepCell()
        m.submodules.src2_c = src2_c = DepCell()

        # connect issue
        for c in [dest_c, src1_c, src2_c]:
            m.d.comb += c.issue_i.eq(self.issue_i)

        # connect go_rd / go_wr (dest->wr, src->rd)
        m.d.comb += dest_c.go_i.eq(self.go_wr_i)
        m.d.comb += src1_c.go_i.eq(self.go_rd_i)
        m.d.comb += src2_c.go_i.eq(self.go_rd_i)

        # connect input reg bit (unary)
        for c, reg in [(dest_c, self.dest_i),
                       (src1_c, self.src1_i),
                       (src2_c, self.src2_i)]:
            m.d.comb += c.reg_i.eq(reg)

        # connect up hazard checks: read-after-write and write-after-read
        m.d.comb += dest_c.hazard_i.eq(self.rd_pend_i) # read-after-write
        m.d.comb += src1_c.hazard_i.eq(self.wr_pend_i) # write-after-read
        m.d.comb += src2_c.hazard_i.eq(self.wr_pend_i) # write-after-read

        # connect fwd / reg-sel outputs
        for c, fwd, rsel in [(dest_c, self.dest_fwd_o, self.dest_rsel_o),
                             (src1_c, self.src1_fwd_o, self.src1_rsel_o),
                             (src2_c, self.src2_fwd_o, self.src2_rsel_o)]:
            m.d.comb += fwd.eq(c.fwd_o)
            m.d.comb += rsel.eq(c.rsel_o)

        # to be accumulated to indicate if register is in use (globally)
        # after ORing, is fed back in to rd_pend_i / wr_pend_i
        m.d.comb += self.rd_rsel_o.eq(src1_c.q_o | src2_c.q_o)
        m.d.comb += self.wr_rsel_o.eq(dest_c.q_o)

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
        yield self.dest_rsel_o
        yield self.src1_rsel_o
        yield self.src2_rsel_o
        yield self.dest_fwd_o
        yield self.src1_fwd_o
        yield self.src2_fwd_o

    def ports(self):
        return list(self)


class DependencyRow(Elaboratable):
    def __init__(self, n_reg_col):
        self.n_reg_col = n_reg_col

        # ----
        # fields all match DependencyCell precisely

        self.dest_i = Signal(n_reg_col, reset_less=True)
        self.src1_i = Signal(n_reg_col, reset_less=True)
        self.src2_i = Signal(n_reg_col, reset_less=True)

        self.rd_pend_i = Signal(n_reg_col, reset_less=True)
        self.wr_pend_i = Signal(n_reg_col, reset_less=True)

        self.rd_rsel_o = Signal(n_reg_col, reset_less=True)
        self.wr_rsel_o = Signal(n_reg_col, reset_less=True)

        self.issue_i = Signal(reset_less=True)
        self.go_wr_i = Signal(reset_less=True)
        self.go_rd_i = Signal(reset_less=True)

        self.dest_rsel_o = Signal(n_reg_col, reset_less=True)
        self.src1_rsel_o = Signal(n_reg_col, reset_less=True)
        self.src2_rsel_o = Signal(n_reg_col, reset_less=True)

        self.dest_fwd_o = Signal(n_reg_col, reset_less=True)
        self.src1_fwd_o = Signal(n_reg_col, reset_less=True)
        self.src2_fwd_o = Signal(n_reg_col, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        rcell = Array(DependenceCell() for f in range(self.n_reg_col))
        for rn in range(self.n_reg_col):
            setattr(m.submodules, "dm_r%d" % rn, rcell[rn])

        # ---
        # connect Dep dest/src to module dest/src
        # ---
        rd_pend_i = []
        wr_pend_i = []
        rd_rsel_o = []
        wr_rsel_o = []
        dest_i = []
        src1_i = []
        src2_i = []
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            # accumulate cell inputs dest/src1/src2
            rd_pend_i.append(dc.rd_pend_i)
            wr_pend_i.append(dc.wr_pend_i)
            rd_rsel_o.append(dc.rd_rsel_o)
            wr_rsel_o.append(dc.wr_rsel_o)
            dest_i.append(dc.dest_i)
            src1_i.append(dc.src1_i)
            src2_i.append(dc.src2_i)
        # wire up inputs from module to row cell inputs (Cat is gooood)
        m.d.comb += [Cat(*dest_i).eq(self.dest_i),
                     Cat(*src1_i).eq(self.src1_i),
                     Cat(*src2_i).eq(self.src2_i),
                     Cat(*rd_pend_i).eq(self.rd_pend_i),
                     Cat(*wr_pend_i).eq(self.wr_pend_i),
                     self.rd_rsel_o.eq(Cat(*rd_rsel_o)),
                     self.wr_rsel_o.eq(Cat(*wr_rsel_o)),
                    ]

        # ---
        # connect Dep issue_i/go_rd_i/go_wr_i to module issue_i/go_rd/go_wr
        # ---
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            m.d.comb += [dc.go_rd_i.eq(self.go_rd_i),
                         dc.go_wr_i.eq(self.go_wr_i),
                         dc.issue_i.eq(self.issue_i),
                    ]

        # ---
        # connect Function Unit vector
        # ---
        dest_fwd_o = []
        src1_fwd_o = []
        src2_fwd_o = []
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            # accumulate cell fwd outputs for dest/src1/src2
            dest_fwd_o.append(dc.dest_fwd_o)
            src1_fwd_o.append(dc.src1_fwd_o)
            src2_fwd_o.append(dc.src2_fwd_o)
        # connect cell fwd outputs to FU Vector Out [Cat is gooood]
        m.d.comb += [self.dest_fwd_o.eq(Cat(*dest_fwd_o)),
                     self.src1_fwd_o.eq(Cat(*src1_fwd_o)),
                     self.src2_fwd_o.eq(Cat(*src2_fwd_o))
                    ]

        # ---
        # connect Reg Selection vector
        # ---
        dest_rsel_o = []
        src1_rsel_o = []
        src2_rsel_o = []
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            # accumulate cell reg-select outputs dest/src1/src2
            dest_rsel_o.append(dc.dest_rsel_o)
            src1_rsel_o.append(dc.src1_rsel_o)
            src2_rsel_o.append(dc.src2_rsel_o)
        # connect cell reg-select outputs to Reg Vector Out
        m.d.comb += self.dest_rsel_o.eq(Cat(*dest_rsel_o))
        m.d.comb += self.src1_rsel_o.eq(Cat(*src1_rsel_o))
        m.d.comb += self.src2_rsel_o.eq(Cat(*src2_rsel_o))

        return m

    def __iter__(self):
        yield self.dest_i
        yield self.src1_i
        yield self.src2_i
        yield self.issue_i
        yield self.go_wr_i
        yield self.go_rd_i
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

    dut = DependenceCell()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
