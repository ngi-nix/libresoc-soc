from nmigen import Elaboratable, Module, Signal, Array


class FU_RW_Pend(Elaboratable):
    """ these are allocated per-FU (horizontally),
        and are of length reg_count
    """
    def __init__(self, reg_count, n_src):
        self.n_src = n_src
        self.reg_count = reg_count
        self.dest_fwd_i = Signal(reg_count, reset_less=True)
        src = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            src.append(Signal(reg_count, name="src%d" % j, reset_less=True))
        self.src_fwd_i = Array(src)

        self.reg_wr_pend_o = Signal(reset_less=True)
        self.reg_rd_pend_o = Signal(reset_less=True)
        self.reg_rd_src_pend_o = Signal(n_src, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.reg_wr_pend_o.eq(self.dest_fwd_i.bool())
        for i in range(self.n_src):
            m.d.comb += self.reg_rd_src_pend_o[i].eq(self.src_fwd_i[i].bool())
        m.d.comb += self.reg_rd_pend_o.eq(self.reg_rd_src_pend_o.bool())
        return m

