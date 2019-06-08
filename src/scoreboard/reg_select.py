from nmigen import Elaboratable, Module, Signal, Array


class Reg_Rsv(Elaboratable):
    """ these are allocated per-Register (vertically),
        and are each of length fu_count
    """
    def __init__(self, fu_count, n_src):
        self.n_src = n_src
        self.fu_count = fu_count
        self.dest_rsel_i = Signal(fu_count, reset_less=True)
        self.src_rsel_i = Array(Signal(fu_count, name="src_rsel_i",
                                       reset_less=True) \
                                for i in range(n_src))
        self.dest_rsel_o = Signal(reset_less=True)
        self.src_rsel_o = Signal(n_src, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.dest_rsel_o.eq(self.dest_rsel_i.bool())
        for i in range(self.n_src):
            m.d.comb += self.src_rsel_o[i].eq(self.src_rsel_i[i].bool())
        return m

