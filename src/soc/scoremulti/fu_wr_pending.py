from nmigen import Elaboratable, Module, Signal, Array


class FU_RW_Pend(Elaboratable):
    """ these are allocated per-FU (horizontally),
        and are of length reg_count
    """
    def __init__(self, reg_count, n_src, n_dest):
        self.n_src = n_src
        self.n_dest = n_dest
        self.reg_count = reg_count
        dst = []
        for i in range(n_dest):
            j = i + 1 # name numbering to match dest1/dest2
            dst.append(Signal(reg_count, name="dfwd%d_i" % j, reset_less=True))
        self.dest_fwd_i = Array(dst)
        src = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            src.append(Signal(reg_count, name="sfwd%d_i" % j, reset_less=True))
        self.src_fwd_i = Array(src)

        self.reg_wr_pend_o = Signal(reset_less=True)
        self.reg_rd_pend_o = Signal(reset_less=True)
        self.reg_rd_src_pend_o = Signal(n_src, reset_less=True)
        self.reg_wr_dst_pend_o = Signal(n_dest, reset_less=True)

    def elaborate(self, platform):
        m = Module()

        # OR forwarding input together to create per-src pending
        for i in range(self.n_src):
            m.d.comb += self.reg_rd_src_pend_o[i].eq(self.src_fwd_i[i].bool())
        # then OR all src pending together
        m.d.comb += self.reg_rd_pend_o.eq(self.reg_rd_src_pend_o.bool())

        # likewise for per-dest then all-dest
        for i in range(self.n_dest):
            m.d.comb += self.reg_wr_dst_pend_o[i].eq(self.dest_fwd_i[i].bool())
        m.d.comb += self.reg_wr_pend_o.eq(self.reg_wr_dst_pend_o.bool())
        return m

