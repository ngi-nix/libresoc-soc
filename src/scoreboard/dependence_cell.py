from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat
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
        m.submodules.dest_l = dest_l = SRLatch() # clock-sync'd
        m.submodules.src1_l = src1_l = SRLatch() # clock-sync'd
        m.submodules.src2_l = src2_l = SRLatch() # clock-sync'd

        # destination latch: reset on go_wr HI, set on dest and issue
        m.d.comb += dest_l.s.eq(self.issue_i & self.dest_i)
        m.d.comb += dest_l.r.eq(self.go_wr_i)

        # src1 latch: reset on go_rd HI, set on src1_i and issue
        m.d.comb += src1_l.s.eq(self.issue_i & self.src1_i)
        m.d.comb += src1_l.r.eq(self.go_rd_i)

        # src2 latch: reset on go_rd HI, set on op2_i and issue
        m.d.comb += src2_l.s.eq(self.issue_i & self.src2_i)
        m.d.comb += src2_l.r.eq(self.go_rd_i)

        # FU "Forward Progress" (read out horizontally)
        m.d.comb += self.dest_fwd_o.eq(dest_l.q & self.go_wr_i)
        m.d.comb += self.src1_fwd_o.eq(src1_l.q & self.go_rd_i)
        m.d.comb += self.src2_fwd_o.eq(src2_l.q & self.go_rd_i)

        # Register File Select (read out vertically)
        m.d.comb += self.dest_rsel_o.eq(dest_l.q & self.dest_i)
        m.d.comb += self.src1_rsel_o.eq(src1_l.q & self.src1_i)
        m.d.comb += self.src2_rsel_o.eq(src2_l.q & self.src2_i)

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


class DependencyRow(Elaboratable):
    def __init__(self, n_reg_col):
        self.n_reg_col = n_reg_col

        # ----
        # fields all match DependencyCell precisely

        self.dest_i = Signal(n_reg_col, reset_less=True)
        self.src1_i = Signal(n_reg_col, reset_less=True)
        self.src2_i = Signal(n_reg_col, reset_less=True)
        self.issue_i = Signal(n_reg_col, reset_less=True)

        self.go_wr_i = Signal(n_reg_col, reset_less=True)
        self.go_rd_i = Signal(n_reg_col, reset_less=True)

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
        dest_i = []
        src1_i = []
        src2_i = []
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            # accumulate cell inputs dest/src1/src2
            dest_i.append(dc.dest_i)
            src1_i.append(dc.src1_i)
            src2_i.append(dc.src2_i)
        # wire up inputs from module to row cell inputs (Cat is gooood)
        m.d.comb += [Cat(*dest_i).eq(self.dest_i),
                     Cat(*src1_i).eq(self.src1_i),
                     Cat(*src2_i).eq(self.src2_i),
                    ]

        # ---
        # connect Dep issue_i/go_rd_i/go_wr_i to module issue_i/go_rd/go_wr
        # ---
        go_rd_i = []
        go_wr_i = []
        issue_i = []
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            # accumulate cell outputs for issue/go_rd/go_wr
            go_rd_i.append(dc.go_rd_i)
            go_wr_i.append(dc.go_wr_i)
            issue_i.append(dc.issue_i)
        # wire up inputs from module to row cell inputs (Cat is gooood)
        m.d.comb += [Cat(*go_rd_i).eq(self.go_rd_i),
                     Cat(*go_wr_i).eq(self.go_wr_i),
                     Cat(*issue_i).eq(self.issue_i),
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
        for rn in range(self.n_reg_col):
            dc = rcell[rn]
            dest_rsel_o = []
            src1_rsel_o = []
            src2_rsel_o = []
            # accumulate cell reg-select outputs dest/src1/src2
            dest_rsel_o.append(dc.dest_rsel_o)
            src1_rsel_o.append(dc.src1_rsel_o)
            src2_rsel_o.append(dc.src2_rsel_o)
        # connect cell reg-select outputs to Reg Vector Out
        m.d.comb += self.dest_rsel_o.eq(Cat(*dest_rsel_o))
        m.d.comb += self.src1_rsel_o.eq(Cat(*src1_rsel_o))
        m.d.comb += self.src2_rsel_o.eq(Cat(*src2_rsel_o))

        return m


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
    dut = DependenceCell()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
