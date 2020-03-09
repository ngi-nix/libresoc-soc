from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat, Const

from soc.scoreboard.fumem_dep_cell import FUMemDependenceCell
from soc.scoreboard.fu_mem_picker_vec import FUMem_Pick_Vec

"""

 6600 Function Unit Dependency Table Matrix inputs / outputs
 -----------------------------------------------------------

"""

class FUMemDepMatrix(Elaboratable):
    """ implements FU-to-FU Memory Dependency Matrix
    """
    def __init__(self, n_fu_row, n_fu_col):
        self.n_fu_row = n_fu_row               # Y (FU row#)   ^v
        self.n_fu_col = n_fu_col                # X (FU col #)  <>
        self.st_pend_i = Signal(n_fu_row, reset_less=True) # Rd pending (left)
        self.ld_pend_i = Signal(n_fu_row, reset_less=True) # Wr pending (left)
        self.issue_i = Signal(n_fu_col, reset_less=True)    # Issue in (top)

        self.go_ld_i = Signal(n_fu_row, reset_less=True) # Go Write in (left)
        self.go_st_i = Signal(n_fu_row, reset_less=True)  # Go Read in (left)
        self.go_die_i = Signal(n_fu_row, reset_less=True) # Go Die in (left)

        # for Function Unit Readable/Writable (horizontal)
        self.storable_o = Signal(n_fu_col, reset_less=True) # storable (bot)
        self.loadable_o = Signal(n_fu_col, reset_less=True) # loadable (bot)

    def elaborate(self, platform):
        m = Module()

        # ---
        # matrix of dependency cells
        # ---
        dm = Array(FUMemDependenceCell(f, self.n_fu_col) \
                                            for f in range(self.n_fu_row))
        for y in range(self.n_fu_row):
                setattr(m.submodules, "dm%d" % y, dm[y])

        # ---
        # array of Function Unit Readable/Writable: row-length, horizontal
        # ---
        fur = Array(FUMem_Pick_Vec(self.n_fu_row) for r in range(self.n_fu_col))
        for x in range(self.n_fu_col):
            setattr(m.submodules, "fur_x%d" % (x), fur[x])

        # ---
        # connect FU Readable/Writable vector
        # ---
        storable = []
        loadable = []
        for y in range(self.n_fu_row):
            fu = fur[y]
            # accumulate Readable/Writable Vector outputs
            storable.append(fu.storable_o)
            loadable.append(fu.loadable_o)

        # ... and output them from this module (horizontal, width=REGs)
        m.d.comb += self.storable_o.eq(Cat(*storable))
        m.d.comb += self.loadable_o.eq(Cat(*loadable))

        # ---
        # connect FU Pending
        # ---
        for y in range(self.n_fu_row):
            dc = dm[y]
            fu = fur[y]
            # connect cell reg-select outputs to Reg Vector In
            m.d.comb += [fu.st_pend_i.eq(dc.st_wait_o),
                         fu.ld_pend_i.eq(dc.ld_wait_o),
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
        # connect Matrix go_st_i/go_ld_i to module storable/loadable
        # ---
        for y in range(self.n_fu_row):
            dc = dm[y]
            # wire up inputs from module to row cell inputs
            m.d.comb += [dc.go_st_i.eq(self.go_st_i),
                         dc.go_ld_i.eq(self.go_ld_i),
                         dc.go_die_i.eq(self.go_die_i),
                        ]

        # ---
        # connect Matrix pending
        # ---
        for y in range(self.n_fu_row):
            dc = dm[y]
            # wire up inputs from module to row cell inputs
            m.d.comb += [dc.st_pend_i.eq(self.st_pend_i),
                         dc.ld_pend_i.eq(self.ld_pend_i),
                        ]

        return m

    def __iter__(self):
        yield self.st_pend_i
        yield self.ld_pend_i
        yield self.issue_i
        yield self.go_ld_i
        yield self.go_st_i
        yield self.storable_o
        yield self.loadable_o
                
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

def test_fu_fu_matrix():
    dut = FUMemDepMatrix(n_fu_row=3, n_fu_col=3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_mem_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_fu_mem_matrix.vcd')

if __name__ == '__main__':
    test_fu_fu_matrix()
