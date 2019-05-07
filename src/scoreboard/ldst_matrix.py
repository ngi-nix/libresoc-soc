""" Mitch Alsup 6600-style LD/ST Memory Scoreboard Matrix (sparse vector)

6600 LD/ST Dependency Table Matrix inputs / outputs
---------------------------------------------------

Relevant comments (p45-46):

* If there are no WAR dependencies on a Load instruction with a computed
  address it can assert Bank_Addressable and Translate_Addressable.

* If there are no RAW dependencies on a Store instruction with both a
  write permission and store data present it can assert Bank_Addressable

Relevant bugreports:
* http://bugs.libre-riscv.org/show_bug.cgi?id=81

"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat, Const

from ldst_dep_cell import LDSTDepCell


class LDSTDepMatrix(Elaboratable):
    """ implements 11.4.12 mitch alsup LD/ST Dependency Matrix, p46
        actually a sparse matrix along the diagonal.

        load-hold-store and store-hold-load accumulate in a priority-picking
        fashion, ORing together.  the OR gate from the dependency cell is
        here.
    """
    def __init__(self, n_ldst):
        self.n_ldst = n_ldst                  # X and Y (FUs)
        self.load_i = Signal(n_ldst, reset_less=True)  # load pending in
        self.stor_i = Signal(n_ldst, reset_less=True)  # store pending in
        self.issue_i = Signal(n_ldst, reset_less=True) # Issue in

        self.load_hit_i = Signal(n_ldst, reset_less=True) # load hit in
        self.stwd_hit_i = Signal(n_ldst, reset_less=True) # store w/data hit in

        # outputs
        self.ld_hold_st_o = Signal(reset_less=True) # load holds st out
        self.st_hold_ld_o = Signal(reset_less=True) # st holds load out

    def elaborate(self, platform):
        m = Module()

        # ---
        # matrix of dependency cells
        # ---
        dm = Array(LDSTDepCell() for f in range(self.n_ldst))
        for fu in range(self.n_ldst):
            setattr(m.submodules, "dm_fu%d" % (fu), dm[fu])

        # ---
        # connect Function Unit vector
        # ---
        lhs_l = []
        shl_l = []
        load_l = []
        stor_l = []
        issue_l = []
        lh_l = []
        sh_l = []
        for fu in range(self.n_ldst):
            dc = dm[fu]
            # accumulate load-hold-store / store-hold-load bits
            lhs_l.append(dc.ld_hold_st_o)
            shl_l.append(dc.st_hold_ld_o)
            # accumulate inputs (for Cat'ing later) - TODO: must be a better way
            load_l.append(dc.load_i)
            stor_l.append(dc.stor_i)
            issue_l.append(dc.issue_i)
            lh_l.append(dc.load_hit_i)
            sh_l.append(dc.stwd_hit_i)

        # connect cell inputs using Cat(*list_of_stuff)
        m.d.comb += [Cat(*load_l).eq(self.load_i),
                     Cat(*stor_l).eq(self.stor_i),
                     Cat(*issue_l).eq(self.issue_i),
                     Cat(*lh_l).eq(self.load_hit_i),
                     Cat(*sh_l).eq(self.stwd_hit_i),
                    ]
        # set the load-hold-store / store-hold-load OR-accumulated outputs
        m.d.comb += self.ld_hold_st_o.eq(Cat(*lhs_l).bool())
        m.d.comb += self.st_hold_ld_o.eq(Cat(*shl_l).bool())

        return m

    def __iter__(self):
        yield self.load_i
        yield self.stor_i
        yield self.issue_i
        yield self.load_hit_i
        yield self.stwd_hit_i
        yield self.ld_hold_st_o
        yield self.st_hold_ld_o

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
    dut = LDSTDepMatrix(n_ldst=4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ld_st_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_ld_st_matrix.vcd')

if __name__ == '__main__':
    test_d_matrix()
