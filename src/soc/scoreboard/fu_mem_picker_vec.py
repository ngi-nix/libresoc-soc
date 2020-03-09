from nmigen import Elaboratable, Module, Signal, Cat


class FUMem_Pick_Vec(Elaboratable):
    """ these are allocated per-FU (horizontally),
        and are of length fu_row_n
    """
    def __init__(self, fu_row_n):
        self.fu_row_n = fu_row_n
        self.st_pend_i = Signal(fu_row_n, reset_less=True)
        self.ld_pend_i = Signal(fu_row_n, reset_less=True)

        self.storable_o = Signal(reset_less=True)
        self.loadable_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()

        # Readable if there are no writes pending
        m.d.comb += self.storable_o.eq(~self.ld_pend_i.bool())

        # Writable if there are no reads pending
        m.d.comb += self.loadable_o.eq(~self.st_pend_i.bool())

        return m

