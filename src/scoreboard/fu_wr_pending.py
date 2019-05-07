from nmigen import Elaboratable, Module, Signal, Cat


class FU_RW_Pend(Elaboratable):
    """ these are allocated per-FU (horizontally),
        and are of length reg_count
    """
    def __init__(self, reg_count):
        self.reg_count = reg_count
        self.dest_fwd_i = Signal(reg_count, reset_less=True)
        self.src1_fwd_i = Signal(reg_count, reset_less=True)
        self.src2_fwd_i = Signal(reg_count, reset_less=True)

        self.reg_wr_pend_o = Signal(reset_less=True)
        self.reg_rd_pend_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        srces = Cat(self.src1_fwd_i, self.src2_fwd_i)
        m.d.comb += self.reg_wr_pend_o.eq(self.dest_fwd_i.bool())
        m.d.comb += self.reg_rd_pend_o.eq(srces.bool())
        return m

