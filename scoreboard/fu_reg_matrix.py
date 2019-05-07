from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat

#from nmutil.latch import SRLatch
from dependence_cell import DependenceCell
from fu_wr_pending import FU_RW_Pend
from reg_select import Reg_Rsv

"""

 6600 Dependency Table Matrix inputs / outputs
 ---------------------------------------------

                d s1 s2 i  d s1 s2 i  d s1 s2 i  d s1 s2 i 
                | |   | |  | |   | |  | |   | |  | |   | | 
                v v   v v  v v   v v  v v   v v  v v   v v 
 go_rd/go_wr -> dm-r0-fu0  dm-r1-fu0  dm-r2-fu0  dm-r3-fu0 -> wr/rd-pend
 go_rd/go_wr -> dm-r0-fu1  dm-r1-fu1  dm-r2-fu1  dm-r3-fu1 -> wr/rd-pend
 go_rd/go_wr -> dm-r0-fu2  dm-r1-fu2  dm-r2-fu2  dm-r3-fu2 -> wr/rd-pend
                 |  |  |    |  |  |    |  |  |    |  |  |
                 v  v  v    v  v  v    v  v  v    v  v  v
                 d  s1 s2   d  s1 s2   d  s1 s2   d  s1 s2
                 reg sel    reg sel    reg sel    reg sel

"""

class FURegDepMatrix(Elaboratable):
    """ implements 11.4.7 mitch alsup FU-to-Reg Dependency Matrix, p26
    """
    def __init__(self, n_fu_row, n_reg_col):
        self.n_fu_row = n_fu_row                  # Y (FUs)   ^v
        self.n_reg_col = n_reg_col                # X (Regs)  <>
        self.dest_i = Signal(n_reg_col, reset_less=True)     # Dest in (top)
        self.src1_i = Signal(n_reg_col, reset_less=True)     # oper1 in (top)
        self.src2_i = Signal(n_reg_col, reset_less=True)     # oper2 in (top)
        self.issue_i = Signal(n_reg_col, reset_less=True)    # Issue in (top)

        self.go_write_i = Signal(n_fu_row, reset_less=True) # Go Write in (left)
        self.go_read_i = Signal(n_fu_row, reset_less=True)  # Go Read in (left)

        # for Register File Select Lines (horizontal), per-reg
        self.dest_rsel_o = Signal(n_reg_col, reset_less=True) # dest reg (bot)
        self.src1_rsel_o = Signal(n_reg_col, reset_less=True) # src1 reg (bot)
        self.src2_rsel_o = Signal(n_reg_col, reset_less=True) # src2 reg (bot)

        # for Function Unit "forward progress" (vertical), per-FU
        self.wr_pend_o = Signal(n_fu_row, reset_less=True) # wr pending (right)
        self.rd_pend_o = Signal(n_fu_row, reset_less=True) # rd pending (right)

    def elaborate(self, platform):
        m = Module()

        # ---
        # matrix of dependency cells
        # ---
        dm = Array(Array(DependenceCell() for r in range(self.n_fu_row)) \
                                          for f in range(self.n_reg_col))
        for rn in range(self.n_reg_col):
            for fu in range(self.n_fu_row):
                setattr(m.submodules, "dm_r%d_fu%d" % (rn, fu), dm[rn][fu])

        # ---
        # array of Function Unit Pending vectors
        # ---
        fupend = Array(FU_RW_Pend(self.n_reg_col) for f in range(self.n_fu_row))
        for fu in range(self.n_fu_row):
            setattr(m.submodules, "fu_fu%d" % (fu), fupend[fu])

        # ---
        # array of Register Reservation vectors
        # ---
        regrsv = Array(Reg_Rsv(self.n_fu_row) for r in range(self.n_reg_col))
        for rn in range(self.n_reg_col):
            setattr(m.submodules, "rr_r%d" % (rn), regrsv[rn])

        # ---
        # connect Function Unit vector
        # ---
        wr_pend = []
        rd_pend = []
        for fu in range(self.n_fu_row):
            fup = fupend[fu]
            dest_fwd_o = []
            src1_fwd_o = []
            src2_fwd_o = []
            for rn in range(self.n_reg_col):
                dc = dm[rn][fu]
                # accumulate cell fwd outputs for dest/src1/src2 
                dest_fwd_o.append(dc.dest_fwd_o)
                src1_fwd_o.append(dc.src1_fwd_o)
                src2_fwd_o.append(dc.src2_fwd_o)
            # connect cell fwd outputs to FU Vector in [Cat is gooood]
            m.d.comb += [fup.dest_fwd_i.eq(Cat(*dest_fwd_o)),
                         fup.src1_fwd_i.eq(Cat(*src1_fwd_o)),
                         fup.src2_fwd_i.eq(Cat(*src2_fwd_o))
                        ]
            # accumulate FU Vector outputs
            wr_pend.append(fup.reg_wr_pend_o)
            rd_pend.append(fup.reg_rd_pend_o)

        # ... and output them from this module (vertical, width=FUs)
        m.d.comb += self.wr_pend_o.eq(Cat(*wr_pend))
        m.d.comb += self.rd_pend_o.eq(Cat(*rd_pend))

        # ---
        # connect Reg Selection vector
        # ---
        dest_rsel = []
        src1_rsel = []
        src2_rsel = []
        for rn in range(self.n_reg_col):
            rsv = regrsv[rn]
            dest_rsel_o = []
            src1_rsel_o = []
            src2_rsel_o = []
            for fu in range(self.n_fu_row):
                dc = dm[rn][fu]
                # accumulate cell reg-select outputs dest/src1/src2
                dest_rsel_o.append(dc.dest_rsel_o)
                src1_rsel_o.append(dc.src1_rsel_o)
                src2_rsel_o.append(dc.src2_rsel_o)
            # connect cell reg-select outputs to Reg Vector In
            m.d.comb += [rsv.dest_rsel_i.eq(Cat(*dest_rsel_o)),
                         rsv.src1_rsel_i.eq(Cat(*src1_rsel_o)),
                         rsv.src2_rsel_i.eq(Cat(*src2_rsel_o)),
                        ]
            # accumulate Reg-Sel Vector outputs
            dest_rsel.append(rsv.dest_rsel_o)
            src1_rsel.append(rsv.src1_rsel_o)
            src2_rsel.append(rsv.src2_rsel_o)

        # ... and output them from this module (horizontal, width=REGs)
        m.d.comb += self.dest_rsel_o.eq(Cat(*dest_rsel))
        m.d.comb += self.src1_rsel_o.eq(Cat(*src1_rsel))
        m.d.comb += self.src2_rsel_o.eq(Cat(*src2_rsel))

        # ---
        # connect Dependency Matrix dest/src1/src2/issue to module d/s/s/i
        # ---
        for rn in range(self.n_reg_col):
            dest_i = []
            src1_i = []
            src2_i = []
            issue_i = []
            for fu in range(self.n_fu_row):
                dc = dm[rn][fu]
                # accumulate cell inputs dest/src1/src2
                dest_i.append(dc.dest_i)
                src1_i.append(dc.src1_i)
                src2_i.append(dc.src2_i)
                issue_i.append(dc.issue_i)
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += [Cat(*dest_i).eq(self.dest_i),
                         Cat(*src1_i).eq(self.src1_i),
                         Cat(*src2_i).eq(self.src2_i),
                         Cat(*issue_i).eq(self.issue_i),
                        ]

        # ---
        # connect Dependency Matrix go_read_i/go_write_i to module go_rd/go_wr
        # ---
        for fu in range(self.n_fu_row):
            go_read_i = []
            go_write_i = []
            for rn in range(self.n_reg_col):
                dc = dm[rn][fu]
                # accumulate cell fwd outputs for dest/src1/src2 
                go_read_i.append(dc.go_read_i)
                go_write_i.append(dc.go_write_i)
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += [Cat(*go_read_i).eq(self.go_read_i),
                         Cat(*go_write_i).eq(self.go_write_i),
                        ]

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
        yield self.wr_pend_o
        yield self.rd_pend_o
                
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

def test_d_matrix():
    dut = FURegDepMatrix(n_fu_row=3, n_reg_col=4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_reg_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_fu_reg_matrix.vcd')

if __name__ == '__main__':
    test_d_matrix()
