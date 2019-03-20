from nmigen import Module, Signal
from nmigen.cli import main

class PteEntry():
    def __init__(self, asid_size, pte_size):
        # Internal
        self.asid_start = pte_size
        self.asid_end = pte_size + asid_size

        # Input
        self.i = Signal(asid_size + pte_size)

        # Output
        self.d = Signal(1) # Dirty bit (From pte)
        self.a = Signal(1) # Accessed bit (From pte)
        self.g = Signal(1) # Global Access (From pte)
        self.u = Signal(1) # User Mode (From pte)
        self.xwr = Signal(3) # Execute Read Write (From pte)
        self.v = Signal(1) # Valid (From pte)
        self.asid = Signal(asid_size) # Associated Address Space IDentifier
        self.pte = Signal(pte_size) # Full Page Table Entry

    def elaborate(self, platform=None):
        m = Module()
        # Pull out all control bites from PTE
        m.d.comb += [
            self.d.eq(self.i[7]),
            self.a.eq(self.i[6]),
            self.g.eq(self.i[5]),
            self.u.eq(self.i[4]),
            self.xwr.eq(self.i[1:4]),
            self.v.eq(self.i[0])
        ]
        m.d.comb += self.asid.eq(self.i[self.asid_start:self.asid_end])
        m.d.comb += self.pte.eq(self.i[0:self.asid_start])
        return m