from nmigen import Module, Signal, Elaboratable
from nmigen.cli import main


class PteEntry(Elaboratable):
    """ The purpose of this Module is to  centralize the parsing of Page
        Table Entries (PTE) into one module to prevent common mistakes
        and duplication of code. The control bits are parsed out for
        ease of use.

        This module parses according to the standard PTE given by the
        Volume II: RISC-V Privileged Architectures V1.10 Pg 60.
        The Address Space IDentifier (ASID) is appended to the MSB of the input
        and is parsed out as such.

        An valid input Signal would be:
              ASID   PTE
        Bits:[78-64][63-0]

        The output PTE value will include the control bits.
    """
    def __init__(self, asid_size, pte_size):
        """ Arguments:
            * asid_size: (bit count) The size of the asid to be processed
            * pte_size: (bit count) The size of the pte to be processed

            Return:
            * d The Dirty bit from the PTE portion of i
            * a The Accessed bit from the PTE portion of i
            * g The Global bit from the PTE portion of i
            * u The User Mode bit from the PTE portion of i
            * xwr The Execute/Write/Read bit from the PTE portion of i
            * v The Valid bit from the PTE portion of i
            * asid The asid portion of i
            * pte The pte portion of i
        """
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
