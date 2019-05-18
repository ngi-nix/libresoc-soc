from nmigen import Elaboratable, Module, Signal, Cat


class FU_Pick_Vec(Elaboratable):
    """ these are allocated per-FU (horizontally),
        and are of length fu_row_n
    """
    def __init__(self, fu_row_n):
        self.fu_row_n = fu_row_n
        self.rd_pend_i = Signal(fu_row_n, reset_less=True)
        self.wr_pend_i = Signal(fu_row_n, reset_less=True)

        self.readable_o = Signal(reset_less=True)
        self.writable_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.readable_o.eq(self.rd_pend_i.bool())
        m.d.comb += self.writable_o.eq(self.wr_pend_i.bool())
        return m

