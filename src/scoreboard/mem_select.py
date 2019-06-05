from nmigen import Elaboratable, Module, Signal


class Mem_Rsv(Elaboratable):
    """ these are allocated per-Register (vertically),
        and are each of length fu_count
    """
    def __init__(self, fu_count):
        self.fu_count = fu_count
        self.ld_rsel_i = Signal(fu_count, reset_less=True)
        self.st_rsel_i = Signal(fu_count, reset_less=True)
        self.ld_rsel_o = Signal(reset_less=True)
        self.st_rsel_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.ld_rsel_o.eq(self.ld_rsel_i.bool())
        m.d.comb += self.st_rsel_o.eq(self.st_rsel_i.bool())
        return m

