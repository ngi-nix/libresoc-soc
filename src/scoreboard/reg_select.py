from nmigen import Elaboratable, Module, Signal


class Reg_Rsv(Elaboratable):
    """ these are allocated per-Register (vertically),
        and are each of length fu_count
    """
    def __init__(self, fu_count):
        self.fu_count = fu_count
        self.dest_rsel_i = Signal(fu_count, reset_less=True)
        self.src1_rsel_i = Signal(fu_count, reset_less=True)
        self.src2_rsel_i = Signal(fu_count, reset_less=True)
        self.dest_rsel_o = Signal(reset_less=True)
        self.src1_rsel_o = Signal(reset_less=True)
        self.src2_rsel_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.dest_rsel_o.eq(self.dest_rsel_i.bool())
        m.d.comb += self.src1_rsel_o.eq(self.src1_rsel_i.bool())
        m.d.comb += self.src2_rsel_o.eq(self.src2_rsel_i.bool())
        return m

