""" Mitch Alsup 6600-style LD/ST scoreboard Dependency Cell

Relevant bugreports:

* http://bugs.libre-riscv.org/show_bug.cgi?id=81

"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Repl, Elaboratable
from nmutil.latch import SRLatch


class LDSTDepCell(Elaboratable):
    """ implements 11.4.12 mitch alsup load/store dependence cell, p45
    """
    def __init__(self, n_ls=1):
        self.n_ls = n_ls
        # inputs
        self.load_h_i = Signal(reset_less=True)     # load in (left)
        self.stor_h_i = Signal(reset_less=True)     # store in (left)
        self.load_v_i = Signal(n_ls, reset_less=True)     # load in (top)
        self.stor_v_i = Signal(n_ls, reset_less=True)     # store in (top)
        self.issue_i = Signal(reset_less=True)    # Issue in (left)
        self.go_die_i = Signal(reset_less=True)    # Issue in (left)

        # load / store hit - basically connect these to go_wr from LD/STCompUnit
        # LD.go_wr -> load_hit_i, ST.go_wr -> stwd_hit_i.
        self.load_hit_i = Signal(n_ls, reset_less=True) # ld hit in (right)
        self.stwd_hit_i = Signal(n_ls, reset_less=True) # st w/ hit in (right)

        # outputs (latched rd/wr pend)
        self.ld_hold_st_o = Signal(reset_less=True) # ld holds st out (l)
        self.st_hold_ld_o = Signal(reset_less=True) # st holds ld out (l)

    def elaborate(self, platform):
        m = Module()
        m.submodules.war_l = war_l = SRLatch(sync=False, llen=self.n_ls) # WaR
        m.submodules.raw_l = raw_l = SRLatch(sync=False, llen=self.n_ls) # RaW

        # temporaries (repeat-extend)
        issue = Repl(self.issue_i, self.n_ls)
        die = Repl(self.go_die_i, self.n_ls)

        # issue & store & load - used for WAR Setting.  LD is left, ST is top
        i_s = Signal(reset_less=True)
        i_s_l = Signal(self.n_ls, reset_less=True)
        m.d.comb += i_s.eq(issue & self.stor_h_i) # horizontal single-signal
        m.d.comb += i_s_l.eq(Repl(i_s, self.n_ls) & self.load_v_i) # multi, vert

        # issue & load & store - used for RAW Setting.  ST is left, LD is top
        i_l = Signal(reset_less=True)
        i_l_s = Signal(self.n_ls, reset_less=True)
        m.d.comb += i_l.eq(issue & self.load_h_i) # horizontal single-signal
        m.d.comb += i_l_s.eq(Repl(i_l, self.n_ls) & self.stor_v_i) # multi, vert

        # write after read latch: loads block stores
        m.d.comb += war_l.s.eq(i_s_l)
        m.d.comb += war_l.r.eq(die | ~self.load_v_i) # reset on LD

        # read after write latch: stores block loads
        m.d.comb += raw_l.s.eq(i_s_l)
        m.d.comb += raw_l.r.eq(die | ~self.stor_v_i) # reset on ST

        # Hold results (read out horizontally, accumulate in OR fashion)
        m.d.comb += self.ld_hold_st_o.eq((war_l.qn & self.load_hit_i).bool())
        m.d.comb += self.st_hold_ld_o.eq((raw_l.qn & self.stwd_hit_i).bool())

        return m

    def __iter__(self):
        yield self.load_h_i
        yield self.load_v_i
        yield self.stor_h_i
        yield self.stor_h_i
        yield self.issue_i
        yield self.load_hit_i
        yield self.stwd_hit_i
        yield self.ld_hold_st_o
        yield self.st_hold_ld_o

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
    dut = LDSTDepCell()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ldst_dcell.il", "w") as f:
        f.write(vl)

    run_simulation(dut, dcell_sim(dut), vcd_name='test_ldst_dcell.vcd')

if __name__ == '__main__':
    test_dcell()
