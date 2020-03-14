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
from nmigen.lib.coding import Decoder

from nmutil.latch import latchregister, SRLatch


class PartialAddrMatch(Elaboratable):
    """A partial address matcher
    """
    def __init__(self, n_adr, bitwid):
        self.n_adr = n_adr
        self.bitwid = bitwid
        # inputs
        self.addrs_i = Array(Signal(bitwid, name="addr") for i in range(n_adr))
        self.addr_we_i = Signal(n_adr) # write-enable for incoming address
        self.addr_en_i = Signal(n_adr) # address latched in
        self.addr_rs_i = Signal(n_adr) # address deactivated

        # output
        self.addr_nomatch_o = Signal(n_adr, name="nomatch_o")
        self.addr_nomatch_a_o = Array(Signal(n_adr, name="nomatch_array_o") \
                                  for i in range(n_adr))

    def elaborate(self, platform):
        m = Module()
        return self._elaborate(m, platform)

    def _elaborate(self, m, platform):
        comb = m.d.comb
        sync = m.d.sync

        # array of address-latches
        m.submodules.l = self.l = l = SRLatch(llen=self.n_adr, sync=False)
        self.addrs_r = addrs_r = Array(Signal(self.bitwid, name="a_r") \
                                       for i in range(self.n_adr))

        # latch set/reset
        comb += l.s.eq(self.addr_en_i)
        comb += l.r.eq(self.addr_rs_i)

        # copy in addresses (and "enable" signals)
        for i in range(self.n_adr):
            latchregister(m, self.addrs_i[i], addrs_r[i], l.q[i])

        # is there a clash, yes/no
        matchgrp = []
        for i in range(self.n_adr):
            match = []
            for j in range(self.n_adr):
                match.append(self.is_match(i, j))
            comb += self.addr_nomatch_a_o[i].eq(~Cat(*match) & l.q)
            matchgrp.append(self.addr_nomatch_a_o[i] == l.q)
        comb += self.addr_nomatch_o.eq(Cat(*matchgrp) & l.q)
            
        return m

    def is_match(self, i, j):
        if i == j:
            return Const(0) # don't match against self!
        return self.addrs_r[i] == self.addrs_r[j]

    def __iter__(self):
        yield from self.addrs_i
        yield self.addr_we_i
        yield self.addr_en_i
        yield from self.addr_nomatch_a_o
        yield self.addr_nomatch_o

    def ports(self):
        return list(self)


class PartialAddrBitmap(PartialAddrMatch):
    def __init__(self, n_adr, bitwid, bit_len):
        PartialAddrMatch.__init__(self, n_adr, bitwid)
        self.bitlen = bitlen # number of bits to turn into unary

        # inputs: length of the LOAD/STORE
        self.len_i = Array(Signal(bitwid, name="len") for i in range(n_adr))

    def elaborate(self, platform):
        m = PartialAddrMatch.elaborate(self, platform)

        # intermediaries
        addrs_r, l = self.addrs_r, self.l
        expwid = 8 + (1<<self.bitlen) # XXX assume LD/ST no greater than 8
        explen_i = Array(Signal(expwid, name="a_l") \
                                       for i in range(self.n_adr))
        lenexp_r = Array(Signal(expwid, name="a_l") \
                                       for i in range(self.n_adr))

        # the mapping between length, address and lenexp_r is that the
        # length and address creates a bytemap which a LD/ST covers.
        # TODO

        # copy in lengths and latch them
        for i in range(self.n_adr):
            latchregister(m, explen_i[i], lenexp_r[i], l.q[i])

        return m


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
