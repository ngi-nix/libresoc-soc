from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat, Const

from soc.scoremulti.fu_dep_cell import FUDependenceCell
from soc.scoreboard.fu_picker_vec import FU_Pick_Vec

"""

 6600 Function Unit Dependency Table Matrix inputs / outputs
 -----------------------------------------------------------

"""

class FUFUDepMatrix(Elaboratable):
    """ implements 11.4.7 mitch alsup FU-to-Reg Dependency Matrix, p26
    """
    def __init__(self, n_fu_row, n_fu_col, n_src, n_dest):
        self.n_fu_row = n_fu_row                  # Y (FU row#)   ^v
        self.n_fu_col = n_fu_col                # X (FU col #)  <>
        self.n_src = n_src
        self.n_dest = n_dest
        self.rd_pend_i = Signal(n_fu_row, reset_less=True) # Rd pending (left)
        self.wr_pend_i = Signal(n_fu_row, reset_less=True) # Wr pending (left)
        self.issue_i = Signal(n_fu_col, reset_less=True)    # Issue in (top)

        self.go_die_i = Signal(n_fu_row, reset_less=True) # Go Die in (left)
        # set up go_wr and go_wr array
        rd = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            rd.append(Signal(n_fu_row, name="gord%d_i" % j, reset_less=True))
        wr = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            wr.append(Signal(n_fu_row, name="gowr%d_i" % j, reset_less=True))

        self.go_wr_i = Array(wr)  # Go Write in (left)
        self.go_rd_i = Array(rd)  # Go Read in (left)

        # for Function Unit Readable/Writable (horizontal)
        self.readable_o = Signal(n_fu_col, reset_less=True) # readable (bot)
        self.writable_o = Signal(n_fu_col, reset_less=True) # writable (bot)

    def elaborate(self, platform):
        m = Module()

        # ---
        # matrix of dependency cells
        # ---
        dm = Array(FUDependenceCell(f, self.n_fu_col, self.n_src, self.n_dest) \
                                            for f in range(self.n_fu_row))
        for y in range(self.n_fu_row):
                setattr(m.submodules, "dm%d" % y, dm[y])

        # ---
        # array of Function Unit Readable/Writable: row-length, horizontal
        # ---
        fur = Array(FU_Pick_Vec(self.n_fu_row) for r in range(self.n_fu_col))
        for x in range(self.n_fu_col):
            setattr(m.submodules, "fur_x%d" % (x), fur[x])

        # ---
        # connect FU Readable/Writable vector
        # ---
        readable = []
        writable = []
        for y in range(self.n_fu_row):
            fu = fur[y]
            # accumulate Readable/Writable Vector outputs
            readable.append(fu.readable_o)
            writable.append(fu.writable_o)

        # ... and output them from this module (horizontal, width=REGs)
        m.d.comb += self.readable_o.eq(Cat(*readable))
        m.d.comb += self.writable_o.eq(Cat(*writable))

        # ---
        # connect FU Pending
        # ---
        for y in range(self.n_fu_row):
            dc = dm[y]
            fu = fur[y]
            # connect cell reg-select outputs to Reg Vector In
            m.d.comb += [fu.rd_pend_i.eq(dc.rd_wait_o),
                         fu.wr_pend_i.eq(dc.wr_wait_o),
                        ]

        # ---
        # connect Dependency Matrix dest/src1/src2/issue to module d/s/s/i
        # ---
        for x in range(self.n_fu_col):
            issue_i = []
            for y in range(self.n_fu_row):
                dc = dm[y]
                # accumulate cell inputs issue
                issue_i.append(dc.issue_i[x])
            # wire up inputs from module to row cell inputs
            m.d.comb += Cat(*issue_i).eq(self.issue_i)

        # ---
        # connect Matrix go_rd_i/go_wr_i to module readable/writable
        # ---
        for y in range(self.n_fu_row):
            dc = dm[y]
            # wire up inputs from module to row cell inputs
            m.d.comb += dc.go_die_i.eq(self.go_die_i)
            for i in range(self.n_src):
                m.d.comb += dc.go_rd_i[i].eq(self.go_rd_i[i])
            for i in range(self.n_dest):
                m.d.comb += dc.go_wr_i[i].eq(self.go_wr_i[i])

        # ---
        # connect Matrix pending
        # ---
        for y in range(self.n_fu_row):
            dc = dm[y]
            # wire up inputs from module to row cell inputs
            m.d.comb += [dc.rd_pend_i.eq(self.rd_pend_i),
                         dc.wr_pend_i.eq(self.wr_pend_i),
                        ]

        return m

    def __iter__(self):
        yield self.rd_pend_i
        yield self.wr_pend_i
        yield self.issue_i
        yield self.go_die_i
        yield from self.go_wr_i
        yield from self.go_rd_i
        yield self.readable_o
        yield self.writable_o
                
    def ports(self):
        return list(self)

def d_matrix_sim(dut):
    """ XXX TODO
    """
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

def test_fu_fu_matrix():
    dut = FUFUDepMatrix(n_fu_row=30, n_fu_col=30, n_src=3, n_dest=2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_fu_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_fu_fu_matrix.vcd')

if __name__ == '__main__':
    test_fu_fu_matrix()
