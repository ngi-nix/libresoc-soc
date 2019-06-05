from nmigen import Elaboratable, Module, Signal, Cat


class MemFU_Pend(Elaboratable):
    """ these are allocated per-FU (horizontally),
        and are of length reg_count
    """
    def __init__(self, reg_count):
        self.reg_count = reg_count
        self.ld_fwd_i = Signal(reg_count, reset_less=True)
        self.st_fwd_i = Signal(reg_count, reset_less=True)

        self.reg_ld_pend_o = Signal(reset_less=True)
        self.reg_st_pend_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.reg_ld_pend_o.eq(self.ld_fwd_i.bool())
        m.d.comb += self.reg_st_pend_o.eq(self.st_fwd_i.bool())

        return m

