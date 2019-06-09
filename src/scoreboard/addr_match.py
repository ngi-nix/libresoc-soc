""" Load / Store partial address matcher

Loads and Stores do not need a full match (CAM), they need "good enough"
avoidance.  Around 11 bits on a 64-bit address is "good enough".

The simplest way to use this module is to ignore not only the top bits,
but also the bottom bits as well: in this case (this RV64 processor),
enough to cover a DWORD (64-bit).  that means ignore the bottom 4 bits,
due to the possibility of 64-bit LD/ST being misaligned.

To reiterate: the use of this module is an *optimisation*.  All it has
to do is cover the cases that are *definitely* matches (by checking 11
bits or so), and if a few opportunities for parallel LD/STs are missed
because the top (or bottom) bits weren't checked, so what: all that
happens is: the mis-matched addresses are LD/STd on single-cycles. Big Deal.

However, if we wanted to enhance this algorithm (without using a CAM and
without using expensive comparators) probably the best way to do so would
be to turn the last 16 bits into a byte-level bitmap.  LD/ST on a byte
would have 1 of the 16 bits set.  LD/ST on a DWORD would have 8 of the 16
bits set (offset if the LD/ST was misaligned).  TODO.

Notes:

> I have used bits <11:6> as they are not translated (4KB pages)
> and larger than a cache line (64 bytes).
> I have used bits <11:4> when the L1 cache was QuadW sized and
> the L2 cache was Line sized.
"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Const, Array, Cat, Elaboratable

from nmutil.latch import latchregister


class PartialAddrMatch(Elaboratable):
    """A partial address matcher
    """
    def __init__(self, n_adr, bitwid):
        self.n_adr = n_adr
        self.bitwid = bitwid
        # inputs
        self.addrs_i = Array(Signal(bitwid, name="addr") for i in range(n_adr))
        self.addr_we_i = Signal(n_adr) # write-enable for incoming address
        self.addr_en_i = Signal(n_adr) # address activated (0 == ignore)

        # output
        self.addr_match_o = Array(Signal(n_adr, name="match_o") \
                                  for i in range(n_adr))

    def elaborate(self, platform):
        m = Module()
        return self._elaborate(m, platform)

    def _elaborate(self, m, platform):
        comb = m.d.comb
        sync = m.d.sync

        addrs_r = Array(Signal(self.bitwid, "a_r") for i in range(self.n_adr))
        ae_r = Signal(self.n_adr)

        # copy in addresses (and "enable" signals)
        for i in range(self.n_adr):
            latchregister(m, self.addrs_i[i], addrs_r[i], self.addr_we_i[i])
            latchregister(m, self.addr_en_i[i], ae_r[i], self.addr_we_i[i])

        # is there a clash, yes/no
        for i in range(self.n_adr):
            match = []
            for j in range(self.n_adr):
                if i == j:
                    match.append(Const(0)) # don't match against self!
                else:
                    match.append(addrs_r[i] == addrs_r[j])
            comb += self.addr_match_o[i].eq(Cat(*match) & ae_r)
            
        return m

    def __iter__(self):
        yield from self.addrs_i
        yield self.addr_we_i
        yield self.addr_en_i
        yield from self.addr_match_o

    def ports(self):
        return list(self)


def part_addr_sim(dut):
    yield dut.dest_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.src1_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.go_rd_i.eq(1)
    yield
    yield dut.go_rd_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield

def test_part_addr():
    dut = PartialAddrMatch(3, 10)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_part_addr.il", "w") as f:
        f.write(vl)

    run_simulation(dut, part_addr_sim(dut), vcd_name='test_part_addr.vcd')

if __name__ == '__main__':
    test_part_addr()
