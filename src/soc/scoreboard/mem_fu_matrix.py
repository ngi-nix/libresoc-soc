from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat

from soc.scoreboard.mem_dependence_cell import MemDepRow
from soc.scoreboard.mem_fu_pending import MemFU_Pend
from soc.scoreboard.mem_select import Mem_Rsv
from soc.scoreboard.global_pending import GlobalPending

"""

"""

class MemFUDepMatrix(Elaboratable):
    """ implements 1st phase Memory-to-FU Dependency Matrix
    """
    def __init__(self, n_fu_row, n_reg_col):
        self.n_fu_row = n_fu_row                  # Y (FUs)   ^v
        self.n_reg_col = n_reg_col                # X (Regs)  <>
        self.ld_i = Signal(n_reg_col, reset_less=True)     # LD in (top)
        self.st_i = Signal(n_reg_col, reset_less=True)     # ST in (top)

        # Register "Global" vectors for determining RaW and WaR hazards
        self.ld_pend_i = Signal(n_reg_col, reset_less=True) # ld pending (top)
        self.st_pend_i = Signal(n_reg_col, reset_less=True) # st pending (top)
        self.v_ld_rsel_o = Signal(n_reg_col, reset_less=True) # ld pending (bot)
        self.v_st_rsel_o = Signal(n_reg_col, reset_less=True) # st pending (bot)

        self.issue_i = Signal(n_fu_row, reset_less=True)  # Issue in (top)
        self.go_ld_i = Signal(n_fu_row, reset_less=True)  # Go LOAD in (left)
        self.go_st_i = Signal(n_fu_row, reset_less=True)  # Go STOR in (left)
        self.go_die_i = Signal(n_fu_row, reset_less=True) # Go Die in (left)

        # for Register File Select Lines (horizontal), per-reg
        self.ld_rsel_o = Signal(n_reg_col, reset_less=True) # ld reg (bot)
        self.st_rsel_o = Signal(n_reg_col, reset_less=True) # st reg (bot)

        # for Function Unit "forward progress" (vertical), per-FU
        self.ld_pend_o = Signal(n_fu_row, reset_less=True) # ld pending (right)
        self.st_pend_o = Signal(n_fu_row, reset_less=True) # st pending (right)

    def elaborate(self, platform):
        m = Module()

        # ---
        # matrix of dependency cells
        # ---
        dm = Array(MemDepRow(self.n_reg_col) for r in range(self.n_fu_row))
        for fu in range(self.n_fu_row):
            setattr(m.submodules, "dr_fu%d" % fu, dm[fu])

        # ---
        # array of Function Unit Pending vectors
        # ---
        fupend = Array(MemFU_Pend(self.n_reg_col) for f in range(self.n_fu_row))
        for fu in range(self.n_fu_row):
            setattr(m.submodules, "fu_fu%d" % (fu), fupend[fu])

        # ---
        # array of Register Reservation vectors
        # ---
        regrsv = Array(Mem_Rsv(self.n_fu_row) for r in range(self.n_reg_col))
        for rn in range(self.n_reg_col):
            setattr(m.submodules, "rr_r%d" % (rn), regrsv[rn])

        # ---
        # connect Function Unit vector
        # ---
        ld_pend = []
        st_pend = []
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            fup = fupend[fu]
            ld_fwd_o = []
            st_fwd_o = []
            for rn in range(self.n_reg_col):
                # accumulate cell fwd outputs for dest/src1
                ld_fwd_o.append(dc.ld_fwd_o[rn])
                st_fwd_o.append(dc.st_fwd_o[rn])
            # connect cell fwd outputs to FU Vector in [Cat is gooood]
            m.d.comb += [fup.ld_fwd_i.eq(Cat(*ld_fwd_o)),
                         fup.st_fwd_i.eq(Cat(*st_fwd_o)),
                        ]
            # accumulate FU Vector outputs
            ld_pend.append(fup.reg_ld_pend_o)
            st_pend.append(fup.reg_st_pend_o)

        # ... and output them from this module (vertical, width=FUs)
        m.d.comb += self.ld_pend_o.eq(Cat(*ld_pend))
        m.d.comb += self.st_pend_o.eq(Cat(*st_pend))

        # ---
        # connect Reg Selection vector
        # ---
        ld_rsel = []
        st_rsel = []
        for rn in range(self.n_reg_col):
            rsv = regrsv[rn]
            ld_rsel_o = []
            st_rsel_o = []
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                # accumulate cell reg-select outputs dest/src1
                ld_rsel_o.append(dc.ld_rsel_o[rn])
                st_rsel_o.append(dc.st_rsel_o[rn])
            # connect cell reg-select outputs to Reg Vector In
            m.d.comb += [rsv.ld_rsel_i.eq(Cat(*ld_rsel_o)),
                         rsv.st_rsel_i.eq(Cat(*st_rsel_o)),
                        ]
            # accumulate Reg-Sel Vector outputs
            ld_rsel.append(rsv.ld_rsel_o)
            st_rsel.append(rsv.st_rsel_o)

        # ... and output them from this module (horizontal, width=REGs)
        m.d.comb += self.ld_rsel_o.eq(Cat(*ld_rsel))
        m.d.comb += self.st_rsel_o.eq(Cat(*st_rsel))

        # ---
        # connect Dependency Matrix dest/src1/issue to module d/s/s/i
        # ---
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += [dc.ld_i.eq(self.ld_i),
                         dc.st_i.eq(self.st_i),
                         dc.st_pend_i.eq(self.st_pend_i),
                         dc.ld_pend_i.eq(self.ld_pend_i),
                        ]

        # accumulate rsel bits into read/write pending vectors.
        st_pend_v = []
        ld_pend_v = []
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            st_pend_v.append(dc.v_st_rsel_o)
            ld_pend_v.append(dc.v_ld_rsel_o)
        st_v = GlobalPending(self.n_reg_col, st_pend_v)
        ld_v = GlobalPending(self.n_reg_col, ld_pend_v)
        m.submodules.st_v = st_v
        m.submodules.ld_v = ld_v

        m.d.comb += self.v_st_rsel_o.eq(st_v.g_pend_o)
        m.d.comb += self.v_ld_rsel_o.eq(ld_v.g_pend_o)

        # ---
        # connect Dep issue_i/go_st_i/go_ld_i to module issue_i/go_rd/go_wr
        # ---
        go_st_i = []
        go_ld_i = []
        go_die_i = []
        issue_i = []
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            # accumulate cell fwd outputs for dest/src1
            go_st_i.append(dc.go_st_i)
            go_ld_i.append(dc.go_ld_i)
            go_die_i.append(dc.go_die_i)
            issue_i.append(dc.issue_i)
        # wire up inputs from module to row cell inputs (Cat is gooood)
        m.d.comb += [Cat(*go_st_i).eq(self.go_st_i),
                     Cat(*go_ld_i).eq(self.go_ld_i),
                     Cat(*go_die_i).eq(self.go_die_i),
                     Cat(*issue_i).eq(self.issue_i),
                    ]

        return m

    def __iter__(self):
        yield self.ld_i
        yield self.st_i
        yield self.issue_i
        yield self.go_ld_i
        yield self.go_st_i
        yield self.go_die_i
        yield self.ld_rsel_o
        yield self.st_rsel_o
        yield self.ld_pend_o
        yield self.st_pend_o
        yield self.ld_pend_i
        yield self.st_pend_i
        yield self.ld_rsel_o
        yield self.st_rsel_o

    def ports(self):
        return list(self)

def d_matrix_sim(dut):
    """ XXX TODO
    """
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

def test_d_matrix():
    dut = MemFUDepMatrix(n_fu_row=3, n_reg_col=3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_mem_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_fu_mem_matrix.vcd')

if __name__ == '__main__':
    test_d_matrix()
