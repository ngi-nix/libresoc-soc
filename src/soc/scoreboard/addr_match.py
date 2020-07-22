""" Load / Store partial address matcher

Related bugreports:
* http://bugs.libre-riscv.org/show_bug.cgi?id=216

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

from nmigen.compat.sim import run_simulation, Settle
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Const, Array, Cat, Elaboratable, Repl
from nmigen.lib.coding import Decoder
from nmigen.utils import log2_int

from nmutil.latch import latchregister, SRLatch


class PartialAddrMatch(Elaboratable):
    """A partial address matcher
    """

    def __init__(self, n_adr, bitwid):
        self.n_adr = n_adr
        self.bitwid = bitwid
        # inputs
        self.addrs_i = Array(Signal(bitwid, name="addr") for i in range(n_adr))
        # self.addr_we_i = Signal(n_adr, reset_less=True) # write-enable
        self.addr_en_i = Signal(n_adr, reset_less=True)  # address latched in
        self.addr_rs_i = Signal(n_adr, reset_less=True)  # address deactivated

        # output: a nomatch for each address plus individual nomatch signals
        self.addr_nomatch_o = Signal(n_adr, name="nomatch_o", reset_less=True)
        self.addr_nomatch_a_o = Array(Signal(n_adr, reset_less=True,
                                             name="nomatch_array_o")
                                      for i in range(n_adr))

    def elaborate(self, platform):
        m = Module()
        return self._elaborate(m, platform)

    def _elaborate(self, m, platform):
        comb = m.d.comb
        sync = m.d.sync

        # array of address-latches
        m.submodules.l = self.l = l = SRLatch(llen=self.n_adr, sync=False)
        self.adrs_r = adrs_r = Array(Signal(self.bitwid, reset_less=True,
                                            name="a_r")
                                     for i in range(self.n_adr))

        # latch set/reset
        comb += l.s.eq(self.addr_en_i)
        comb += l.r.eq(self.addr_rs_i)

        # copy in addresses (and "enable" signals)
        for i in range(self.n_adr):
            latchregister(m, self.addrs_i[i], adrs_r[i], l.q[i])

        # is there a clash, yes/no
        matchgrp = []
        for i in range(self.n_adr):
            match = []
            for j in range(self.n_adr):
                match.append(self.is_match(i, j))
            comb += self.addr_nomatch_a_o[i].eq(~Cat(*match))
            matchgrp.append((self.addr_nomatch_a_o[i] & l.q) == l.q)
        comb += self.addr_nomatch_o.eq(Cat(*matchgrp) & l.q)

        return m

    def is_match(self, i, j):
        if i == j:
            return Const(0)  # don't match against self!
        return self.adrs_r[i] == self.adrs_r[j]

    def __iter__(self):
        yield from self.addrs_i
        # yield self.addr_we_i
        yield self.addr_en_i
        yield from self.addr_nomatch_a_o
        yield self.addr_nomatch_o

    def ports(self):
        return list(self)


class LenExpand(Elaboratable):
    """LenExpand: expands binary length (and LSBs of an address) into unary

    this basically produces a bitmap of which *bytes* are to be read (written)
    in memory.  examples:

    (bit_len=4) len=4, addr=0b0011 => 0b1111 << addr
                                   => 0b1111000
    (bit_len=4) len=8, addr=0b0101 => 0b11111111 << addr
                                   => 0b1111111100000

    note: by setting cover=8 this can also be used as a shift-mask.  the
    bit-mask is replicated (expanded out), each bit expanded to "cover" bits.
    """

    def __init__(self, bit_len, cover=1):
        self.bit_len = bit_len
        self.cover = cover
        self.len_i = Signal(bit_len, reset_less=True)
        self.addr_i = Signal(bit_len, reset_less=True)
        self.lexp_o = Signal(self.llen(1), reset_less=True)
        if cover > 1:
            self.rexp_o = Signal(self.llen(cover), reset_less=True)
        print("LenExpand", bit_len, cover, self.lexp_o.shape())

    def llen(self, cover):
        cl = log2_int(self.cover)
        return (cover << (self.bit_len))+(cl << self.bit_len)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # covers N bits
        llen = self.llen(1)
        # temp
        binlen = Signal((1 << self.bit_len)+1, reset_less=True)
        lexp_o = Signal(llen, reset_less=True)
        comb += binlen.eq((Const(1, self.bit_len+1) << (self.len_i)) - 1)
        comb += self.lexp_o.eq(binlen << self.addr_i)
        if self.cover == 1:
            return m
        l = []
        print("llen", llen)
        for i in range(llen):
            l.append(Repl(self.lexp_o[i], self.cover))
        comb += self.rexp_o.eq(Cat(*l))
        return m

    def ports(self):
        return [self.len_i, self.addr_i, self.lexp_o, ]


class TwinPartialAddrBitmap(PartialAddrMatch):
    """TwinPartialAddrBitMap

    designed to be connected to via LDSTSplitter, which generates
    *pairs* of addresses and covers the misalignment across cache
    line boundaries *in the splitter*.  Also LDSTSplitter takes
    care of expanding the LSBs of each address into a bitmap, itself.

    the key difference between this and PartialAddrMap is that the
    knowledge (fact) that pairs of addresses from the same LDSTSplitter
    are 1 apart is *guaranteed* to be a miss for those two addresses.
    therefore is_match specially takes that into account.
    """

    def __init__(self, n_adr, lsbwid, bitlen):
        self.lsbwid = lsbwid  # number of bits to turn into unary
        self.midlen = bitlen-lsbwid
        PartialAddrMatch.__init__(self, n_adr, self.midlen)

        # input: length of the LOAD/STORE
        expwid = 1+self.lsbwid  # XXX assume LD/ST no greater than 8
        self.lexp_i = Array(Signal(1 << expwid, reset_less=True,
                                   name="len") for i in range(n_adr))
        # input: full address
        self.faddrs_i = Array(Signal(bitlen, reset_less=True,
                                     name="fadr") for i in range(n_adr))

        # registers for expanded len
        self.len_r = Array(Signal(expwid, reset_less=True, name="l_r")
                           for i in range(self.n_adr))

    def elaborate(self, platform):
        m = PartialAddrMatch.elaborate(self, platform)
        comb = m.d.comb

        # intermediaries
        adrs_r, l = self.adrs_r, self.l
        expwid = 1+self.lsbwid

        for i in range(self.n_adr):
            # copy the top lsbwid..(lsbwid-bit_len) of addresses to compare
            comb += self.addrs_i[i].eq(self.faddrs_i[i][self.lsbwid:])

            # copy in expanded-lengths and latch them
            latchregister(m, self.lexp_i[i], self.len_r[i], l.q[i])

        return m

    # TODO make this a module.  too much.
    def is_match(self, i, j):
        if i == j:
            return Const(0)  # don't match against self!
        # we know that pairs have addr and addr+1 therefore it is
        # guaranteed that they will not match.
        if (i // 2) == (j // 2):
            return Const(0)  # don't match against twin, either.

        # the bitmask contains data for *two* cache lines (16 bytes).
        # however len==8 only covers *half* a cache line so we only
        # need to compare half the bits
        expwid = 1 << self.lsbwid
        # if i % 2 == 1 or j % 2 == 1: # XXX hmmm...
        #   expwid >>= 1

        # straight compare: binary top bits of addr, *unary* compare on bottom
        straight_eq = (self.adrs_r[i] == self.adrs_r[j]) & \
                      (self.len_r[i][:expwid] & self.len_r[j][:expwid]).bool()
        return straight_eq

    def __iter__(self):
        yield from self.faddrs_i
        yield from self.lexp_i
        yield self.addr_en_i
        yield from self.addr_nomatch_a_o
        yield self.addr_nomatch_o

    def ports(self):
        return list(self)


class PartialAddrBitmap(PartialAddrMatch):
    """PartialAddrBitMap

    makes two comparisons for each address, with each (addr,len)
    being extended to an unary byte-map.

    two comparisons are needed because when an address is misaligned,
    the byte-map is split into two halves.  example:

    address = 0b1011011, len=8 => 0b101 and shift of 11 (0b1011)
                                  len in unary is 0b0000 0000 1111 1111
                                  when shifted becomes TWO addresses:

    * 0b101   and a byte-map of 0b1111 1000 0000 0000 (len-mask shifted by 11)
    * 0b101+1 and a byte-map of 0b0000 0000 0000 0111 (overlaps onto next 16)

    therefore, because this now covers two addresses, we need *two*
    comparisons per address *not* one.
    """

    def __init__(self, n_adr, lsbwid, bitlen):
        self.lsbwid = lsbwid  # number of bits to turn into unary
        self.midlen = bitlen-lsbwid
        PartialAddrMatch.__init__(self, n_adr, self.midlen)

        # input: length of the LOAD/STORE
        self.len_i = Array(Signal(lsbwid, reset_less=True,
                                  name="len") for i in range(n_adr))
        # input: full address
        self.faddrs_i = Array(Signal(bitlen, reset_less=True,
                                     name="fadr") for i in range(n_adr))

        # intermediary: address + 1
        self.addr1s = Array(Signal(self.midlen, reset_less=True,
                                   name="adr1")
                            for i in range(n_adr))

        # expanded lengths, needed in match
        expwid = 1+self.lsbwid  # XXX assume LD/ST no greater than 8
        self.lexp = Array(Signal(1 << expwid, reset_less=True,
                                 name="a_l")
                          for i in range(self.n_adr))

    def elaborate(self, platform):
        m = PartialAddrMatch.elaborate(self, platform)
        comb = m.d.comb

        # intermediaries
        adrs_r, l = self.adrs_r, self.l
        len_r = Array(Signal(self.lsbwid, reset_less=True,
                             name="l_r")
                      for i in range(self.n_adr))

        for i in range(self.n_adr):
            # create a bit-expander for each address
            be = LenExpand(self.lsbwid)
            setattr(m.submodules, "le%d" % i, be)
            # copy the top lsbwid..(lsbwid-bit_len) of addresses to compare
            comb += self.addrs_i[i].eq(self.faddrs_i[i][self.lsbwid:])

            # copy in lengths and latch them
            latchregister(m, self.len_i[i], len_r[i], l.q[i])

            # add one to intermediate addresses
            comb += self.addr1s[i].eq(self.adrs_r[i]+1)

            # put the bottom bits of each address into each LenExpander.
            comb += be.len_i.eq(len_r[i])
            comb += be.addr_i.eq(self.faddrs_i[i][:self.lsbwid])
            # connect expander output
            comb += self.lexp[i].eq(be.lexp_o)

        return m

    # TODO make this a module.  too much.
    def is_match(self, i, j):
        if i == j:
            return Const(0)  # don't match against self!
        # the bitmask contains data for *two* cache lines (16 bytes).
        # however len==8 only covers *half* a cache line so we only
        # need to compare half the bits
        expwid = 1 << self.lsbwid
        hexp = expwid >> 1
        expwid2 = expwid + hexp
        print(self.lsbwid, expwid)
        # straight compare: binary top bits of addr, *unary* compare on bottom
        straight_eq = (self.adrs_r[i] == self.adrs_r[j]) & \
                      (self.lexp[i][:expwid] & self.lexp[j][:expwid]).bool()
        # compare i (addr+1) to j (addr), but top unary against bottom unary
        i1_eq_j = (self.addr1s[i] == self.adrs_r[j]) & \
                  (self.lexp[i][expwid:expwid2] & self.lexp[j][:hexp]).bool()
        # compare i (addr) to j (addr+1), but bottom unary against top unary
        i_eq_j1 = (self.adrs_r[i] == self.addr1s[j]) & \
                  (self.lexp[i][:hexp] & self.lexp[j][expwid:expwid2]).bool()
        return straight_eq | i1_eq_j | i_eq_j1

    def __iter__(self):
        yield from self.faddrs_i
        yield from self.len_i
        # yield self.addr_we_i
        yield self.addr_en_i
        yield from self.addr_nomatch_a_o
        yield self.addr_nomatch_o

    def ports(self):
        return list(self)


def part_addr_sim(dut):
    return
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


def part_addr_bit(dut):
    #                                    0b110 |               0b101 |
    # 0b101 1011 / 8 ==> 0b0000 0000 0000 0111 | 1111 1000 0000 0000 |
    yield dut.len_i[0].eq(8)
    yield dut.faddrs_i[0].eq(0b1011011)
    yield dut.addr_en_i[0].eq(1)
    yield
    yield dut.addr_en_i[0].eq(0)
    yield
    #                                    0b110 |               0b101 |
    # 0b110 0010 / 2 ==> 0b0000 0000 0000 1100 | 0000 0000 0000 0000 |
    yield dut.len_i[1].eq(2)
    yield dut.faddrs_i[1].eq(0b1100010)
    yield dut.addr_en_i[1].eq(1)
    yield
    yield dut.addr_en_i[1].eq(0)
    yield
    #                                    0b110 |               0b101 |
    # 0b101 1010 / 2 ==> 0b0000 0000 0000 0000 | 0000 1100 0000 0000 |
    yield dut.len_i[2].eq(2)
    yield dut.faddrs_i[2].eq(0b1011010)
    yield dut.addr_en_i[2].eq(1)
    yield
    yield dut.addr_en_i[2].eq(0)
    yield
    #                                    0b110 |               0b101 |
    # 0b101 1001 / 2 ==> 0b0000 0000 0000 0000 | 0000 0110 0000 0000 |
    yield dut.len_i[2].eq(2)
    yield dut.faddrs_i[2].eq(0b1011001)
    yield dut.addr_en_i[2].eq(1)
    yield
    yield dut.addr_en_i[2].eq(0)
    yield
    yield dut.addr_rs_i[1].eq(1)
    yield
    yield dut.addr_rs_i[1].eq(0)
    yield


def part_addr_byte(dut):
    for l in range(8):
        for a in range(1 << dut.bit_len):
            maskbit = (1 << (l))-1
            mask = (1 << (l*8))-1
            yield dut.len_i.eq(l)
            yield dut.addr_i.eq(a)
            yield Settle()
            lexp = yield dut.lexp_o
            exp = yield dut.rexp_o
            print("pa", l, a, bin(lexp), hex(exp))
            assert exp == (mask << (a*8))
            assert lexp == (maskbit << (a))


def test_lenexpand_byte():
    dut = LenExpand(4, 8)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_len_expand_byte.il", "w") as f:
        f.write(vl)
    run_simulation(dut, part_addr_byte(dut), vcd_name='test_part_byte.vcd')


def test_part_addr():
    dut = LenExpand(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_len_expand.il", "w") as f:
        f.write(vl)

    dut = TwinPartialAddrBitmap(3, 4, 10)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_twin_part_bit.il", "w") as f:
        f.write(vl)

    dut = PartialAddrBitmap(3, 4, 10)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_part_bit.il", "w") as f:
        f.write(vl)

    run_simulation(dut, part_addr_bit(dut), vcd_name='test_part_bit.vcd')

    dut = PartialAddrMatch(3, 10)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_part_addr.il", "w") as f:
        f.write(vl)

    run_simulation(dut, part_addr_sim(dut), vcd_name='test_part_addr.vcd')


if __name__ == '__main__':
    test_part_addr()
    test_lenexpand_byte()
