from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable, Array, Cat, Repl

from soc.scoremulti.dependence_cell import DependencyRow
from soc.scoremulti.fu_wr_pending import FU_RW_Pend
from soc.scoremulti.reg_sel import Reg_Rsv
from soc.scoreboard.global_pending import GlobalPending

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
    def __init__(self, n_fu_row, n_reg_col, n_src, n_dest, cancel=None):
        self.n_src = n_src
        self.n_dest = n_dest
        self.n_fu_row = nf = n_fu_row      # Y (FUs)   ^v
        self.n_reg_col = n_reg = n_reg_col   # X (Regs)  <>

        # arrays
        src = []
        rsel = []
        rd = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            src.append(Signal(n_reg, name="src%d" % j, reset_less=True))
            rsel.append(Signal(n_reg, name="src%d_rsel_o" % j, reset_less=True))
            rd.append(Signal(nf, name="gord%d_i" % j, reset_less=True))
        dst = []
        dsel = []
        wr = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            dst.append(Signal(n_reg, name="dst%d" % j, reset_less=True))
            dsel.append(Signal(n_reg, name="dst%d_rsel_o" % j, reset_less=True))
            wr.append(Signal(nf, name="gowr%d_i" % j, reset_less=True))
        wpnd = []
        pend = []
        for i in range(nf):
            j = i + 1 # name numbering to match src1/src2
            pend.append(Signal(nf, name="rd_src%d_pend_o" % j, reset_less=True))
            wpnd.append(Signal(nf, name="wr_dst%d_pend_o" % j, reset_less=True))

        self.dest_i = Array(dst)     # Dest in (top)
        self.src_i = Array(src)      # oper in (top)

        # cancellation array (from Address Matching), ties in with go_die_i
        self.cancel = cancel

        # Register "Global" vectors for determining RaW and WaR hazards
        self.wr_pend_i = Signal(n_reg_col, reset_less=True) # wr pending (top)
        self.rd_pend_i = Signal(n_reg_col, reset_less=True) # rd pending (top)
        self.v_wr_rsel_o = Signal(n_reg_col, reset_less=True) # wr pending (bot)
        self.v_rd_rsel_o = Signal(n_reg_col, reset_less=True) # rd pending (bot)

        self.issue_i = Signal(n_fu_row, reset_less=True)  # Issue in (top)
        self.go_wr_i = Array(wr)  # Go Write in (left)
        self.go_rd_i = Array(rd)  # Go Read in (left)
        self.go_die_i = Signal(n_fu_row, reset_less=True) # Go Die in (left)

        # for Register File Select Lines (horizontal), per-reg
        self.dest_rsel_o = Array(dsel) # dest reg (bot)
        self.src_rsel_o = Array(rsel)  # src reg (bot)

        # for Function Unit "forward progress" (vertical), per-FU

        # global "merged" (all regs) src/dest pending vectors
        self.wr_dst_pend_o = Array(wpnd) # dest pending
        self.rd_src_pend_o = Array(pend) # src1 pending

        # per-port src/dest pending vectors
        self.wr_pend_o = Signal(n_fu_row, reset_less=True) # wr pending (right)
        self.rd_pend_o = Signal(n_fu_row, reset_less=True) # rd pending (right)

    def elaborate(self, platform):
        m = Module()
        return self._elaborate(m, platform)

    def _elaborate(self, m, platform):

        # ---
        # matrix of dependency cells
        # ---
        cancel_mode = self.cancel is not None
        dm = Array(DependencyRow(self.n_reg_col, self.n_src,
                                 self.n_dest, cancel_mode) \
                    for r in range(self.n_fu_row))
        for fu in range(self.n_fu_row):
            setattr(m.submodules, "dr_fu%d" % fu, dm[fu])

        # ---
        # array of Function Unit Pending vectors
        # ---
        fupend = Array(FU_RW_Pend(self.n_reg_col, self.n_src, self.n_dest) \
                        for f in range(self.n_fu_row))
        for fu in range(self.n_fu_row):
            setattr(m.submodules, "fu_fu%d" % (fu), fupend[fu])

        # ---
        # array of Register Reservation vectors
        # ---
        regrsv = Array(Reg_Rsv(self.n_fu_row, self.n_src, self.n_dest) \
                        for r in range(self.n_reg_col))
        for rn in range(self.n_reg_col):
            setattr(m.submodules, "rr_r%d" % (rn), regrsv[rn])

        # ---
        # connect Function Unit vector
        # ---
        wr_pend = []
        rd_pend = []
        for fu in range(self.n_fu_row):
            fup = fupend[fu]
            # accumulate FU Vector outputs
            wr_pend.append(fup.reg_wr_pend_o)
            rd_pend.append(fup.reg_rd_pend_o)

        # ... and output them from this module (vertical, width=FUs)
        m.d.comb += self.wr_pend_o.eq(Cat(*wr_pend))
        m.d.comb += self.rd_pend_o.eq(Cat(*rd_pend))

        # same for dest
        for i in range(self.n_dest):
            wr_dst_pend = []
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                fup = fupend[fu]
                dst_fwd_o = []
                for rn in range(self.n_reg_col):
                    # accumulate cell fwd outputs for dest/src1/src2
                    dst_fwd_o.append(dc.dest_fwd_o[i][rn])
                # connect cell fwd outputs to FU Vector in [Cat is gooood]
                m.d.comb += [fup.dest_fwd_i[i].eq(Cat(*dst_fwd_o)),
                            ]
                # accumulate FU Vector outputs
                wr_dst_pend.append(fup.reg_wr_dst_pend_o[i])
            # ... and output them from this module (vertical, width=FUs)
            m.d.comb += self.wr_dst_pend_o[i].eq(Cat(*wr_dst_pend))

        # same for src
        for i in range(self.n_src):
            rd_src_pend = []
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                fup = fupend[fu]
                src_fwd_o = []
                for rn in range(self.n_reg_col):
                    # accumulate cell fwd outputs for dest/src1/src2
                    src_fwd_o.append(dc.src_fwd_o[i][rn])
                # connect cell fwd outputs to FU Vector in [Cat is gooood]
                m.d.comb += [fup.src_fwd_i[i].eq(Cat(*src_fwd_o)),
                            ]
                # accumulate FU Vector outputs
                rd_src_pend.append(fup.reg_rd_src_pend_o[i])
            # ... and output them from this module (vertical, width=FUs)
            m.d.comb += self.rd_src_pend_o[i].eq(Cat(*rd_src_pend))

        # ---
        # connect Reg Selection vector
        # ---
        for i in range(self.n_dest):
            dest_rsel = []
            for rn in range(self.n_reg_col):
                rsv = regrsv[rn]
                dest_rsel_o = []
                for fu in range(self.n_fu_row):
                    dc = dm[fu]
                    # accumulate cell reg-select outputs dest/src1/src2
                    dest_rsel_o.append(dc.dest_rsel_o[i][rn])
                # connect cell reg-select outputs to Reg Vector In
                m.d.comb += rsv.dest_rsel_i[i].eq(Cat(*dest_rsel_o)),

                # accumulate Reg-Sel Vector outputs
                dest_rsel.append(rsv.dest_rsel_o[i])

        # ... and output them from this module (horizontal, width=REGs)
        m.d.comb += self.dest_rsel_o[i].eq(Cat(*dest_rsel))

        # same for src
        for i in range(self.n_src):
            src_rsel = []
            for rn in range(self.n_reg_col):
                rsv = regrsv[rn]
                src_rsel_o = []
                for fu in range(self.n_fu_row):
                    dc = dm[fu]
                    # accumulate cell reg-select outputs dest/src1/src2
                    src_rsel_o.append(dc.src_rsel_o[i][rn])
                # connect cell reg-select outputs to Reg Vector In
                m.d.comb += rsv.src_rsel_i[i].eq(Cat(*src_rsel_o)),
                # accumulate Reg-Sel Vector outputs
                src_rsel.append(rsv.src_rsel_o[i])

            # ... and output them from this module (horizontal, width=REGs)
            m.d.comb += self.src_rsel_o[i].eq(Cat(*src_rsel))

        # ---
        # connect Dependency Matrix dest/src1/src2/issue to module d/s/s/i
        # ---
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += [dc.rd_pend_i.eq(self.rd_pend_i),
                         dc.wr_pend_i.eq(self.wr_pend_i),
                        ]
        # same for dest
        for i in range(self.n_dest):
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                # wire up inputs from module to row cell inputs (Cat is gooood)
                m.d.comb += dc.dest_i[i].eq(self.dest_i[i])

        # same for src
        for i in range(self.n_src):
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                # wire up inputs from module to row cell inputs (Cat is gooood)
                m.d.comb += dc.src_i[i].eq(self.src_i[i])

        # accumulate rsel bits into read/write pending vectors.
        rd_pend_v = []
        wr_pend_v = []
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            rd_pend_v.append(dc.v_rd_rsel_o)
            wr_pend_v.append(dc.v_wr_rsel_o)
        rd_v = GlobalPending(self.n_reg_col, rd_pend_v)
        wr_v = GlobalPending(self.n_reg_col, wr_pend_v)
        m.submodules.rd_v = rd_v
        m.submodules.wr_v = wr_v

        m.d.comb += self.v_rd_rsel_o.eq(rd_v.g_pend_o)
        m.d.comb += self.v_wr_rsel_o.eq(wr_v.g_pend_o)

        # ---
        # connect Dep issue_i/go_rd_i/go_wr_i to module issue_i/go_rd/go_wr
        # ---
        issue_i = []
        for fu in range(self.n_fu_row):
            dc = dm[fu]
            issue_i.append(dc.issue_i)
        # wire up inputs from module to row cell inputs (Cat is gooood)
        m.d.comb += Cat(*issue_i).eq(self.issue_i)

        for i in range(self.n_src):
            go_rd_i = []
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                # accumulate cell fwd outputs for dest/src1/src2
                go_rd_i.append(dc.go_rd_i[i])
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += Cat(*go_rd_i).eq(self.go_rd_i[i])

        for i in range(self.n_dest):
            go_wr_i = []
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                # accumulate cell fwd outputs for dest/src1/src2
                go_wr_i.append(dc.go_wr_i[i])
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += Cat(*go_wr_i).eq(self.go_wr_i[i])

        # ---
        # connect Dep go_die_i
        # ---
        if cancel_mode:
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                go_die = Repl(self.go_die_i[fu], self.n_fu_row)
                go_die = go_die | self.cancel[fu]
                m.d.comb += dc.go_die_i.eq(go_die)
        else:
            go_die_i = []
            for fu in range(self.n_fu_row):
                dc = dm[fu]
                # accumulate cell fwd outputs for dest/src1/src2
                go_die_i.append(dc.go_die_i)
            # wire up inputs from module to row cell inputs (Cat is gooood)
            m.d.comb += Cat(*go_die_i).eq(self.go_die_i)
        return m

    def __iter__(self):
        yield from self.dest_i
        yield from self.src_i
        yield self.issue_i
        yield from self.go_wr_i
        yield from self.go_rd_i
        yield self.go_die_i
        yield from self.dest_rsel_o
        yield from self.src_rsel_o
        yield self.wr_pend_o
        yield self.rd_pend_o
        yield self.wr_pend_i
        yield self.rd_pend_i
        yield self.v_wr_rsel_o
        yield self.v_rd_rsel_o
        yield from self.rd_src_pend_o

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

def test_d_matrix():
    dut = FURegDepMatrix(n_fu_row=3, n_reg_col=4, n_src=2, n_dest=2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fu_reg_matrix.il", "w") as f:
        f.write(vl)

    run_simulation(dut, d_matrix_sim(dut), vcd_name='test_fu_reg_matrix.vcd')

if __name__ == '__main__':
    test_d_matrix()
