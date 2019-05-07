from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat

#from nmutil.latch import SRLatch
from fu_dep_cell import FUDependenceCell
from fu_picker_vec import FU_Pick_Vec

"""

 6600 Function Unit Dependency Table Matrix inputs / outputs
 -----------------------------------------------------------

"""

class FUFUDepMatrix(Elaboratable):
    """ implements 11.4.7 mitch alsup FU-to-Reg Dependency Matrix, p26
    """
    def __init__(self, n_fu_row, n_fu_col):
        self.n_fu_row = n_fu_row                  # Y (FU row#)   ^v
        self.n_fu_col = n_fu_col                # X (FU col #)  <>
        self.rd_pend_i = Signal(n_fu_row, reset_less=True) # Rd pending (left)
        self.wr_pend_i = Signal(n_fu_row, reset_less=True) # Wr pending (left)
        self.issue_i = Signal(n_fu_col, reset_less=True)    # Issue in (top)

        self.go_write_i = Signal(n_fu_row, reset_less=True) # Go Write in (left)
        self.go_read_i = Signal(n_fu_row, reset_less=True)  # Go Read in (left)

        # for Function Unit Readable/Writable (horizontal)
        self.readable_o = Signal(n_fu_col, reset_less=True) # readable (bot)
        self.writable_o = Signal(n_fu_col, reset_less=True) # writable (bot)

    def elaborate(self, platform):
        m = Module()

        # ---
        # matrix of dependency cells
        # ---
        dm = Array(Array(FUDependenceCell() for r in range(self.n_fu_row)) \
                                            for f in range(self.n_fu_col))
        for x in range(self.n_fu_col):
            for y in range(self.n_fu_row):
                setattr(m.submodules, "dm_fx%d_fy%d" % (x, y), dm[x][y])

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
        for x in range(self.n_fu_col):
            fu = fur[x]
            rd_pend_o = []
            wr_pend_o = []
            for y in range(self.n_fu_row):
                dc = dm[x][y]
                # accumulate cell outputs rd/wr-pending
                rd_pend_o.append(dc.rd_pend_o)
                wr_pend_o.append(dc.wr_pend_o)
            # connect cell reg-select outputs to Reg Vector In
            m.d.comb += [fu.rd_pend_i.eq(Cat(*rd_pend_o)),
                         fu.wr_pend_i.eq(Cat(*wr_pend_o)),
                        ]
            # accumulate Readable/Writable Vector outputs
            readable.append(fu.readable_o)
            writable.append(fu.writable_o)

        # ... and output them from this module (horizontal, width=REGs)
        m.d.comb += self.readable_o.eq(Cat(*readable))
        m.d.comb += self.writable_o.eq(Cat(*writable))

        # ---
        # connect Dependency Matrix dest/src1/src2/issue to module d/s/s/i
        # ---
        for y in range(self.n_fu_row):
            issue_i = []
            for x in range(self.n_fu_col):
                dc = dm[x][y]
                # accumulate cell inputs issue
                issue_i.append(dc.issue_i)
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += Cat(*issue_i).eq(self.issue_i)

        # ---
        # connect Matrix go_read_i/go_write_i to module readable/writable
        # ---
        for x in range(self.n_fu_col):
            go_read_i = []
            go_write_i = []
            rd_pend_i = []
            wr_pend_i = []
            for y in range(self.n_fu_row):
                dc = dm[x][y]
                # accumulate cell rd_pend/wr_pend/go_read/go_write
                rd_pend_i.append(dc.rd_pend_i)
                wr_pend_i.append(dc.wr_pend_i)
                go_read_i.append(dc.go_read_i)
                go_write_i.append(dc.go_write_i)
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += [Cat(*go_read_i).eq(self.go_read_i),
                         Cat(*go_write_i).eq(self.go_write_i),
                         Cat(*rd_pend_i).eq(self.rd_pend_i),
                         Cat(*wr_pend_i).eq(self.wr_pend_i),
                        ]

        return m

    def __iter__(self):
        yield self.rd_pend_i
        yield self.wr_pend_i
        yield self.issue_i
        yield self.go_write_i
        yield self.go_read_i
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
    yield dut.go_read_i.eq(1)
    yield
    yield dut.go_read_i.eq(0)
    yield
    yield dut.go_write_i.eq(1)
    yield
    yield dut.go_write_i.eq(0)
    yield

def test_fu_fu_matrix():
    dut = FUFUDepMatrix(n_fu_row=3, n_fu_col=4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_fu_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_fu_fu_matrix.vcd')

if __name__ == '__main__':
    test_fu_fu_matrix()
