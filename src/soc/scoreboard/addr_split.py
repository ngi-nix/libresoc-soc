# LDST Address Splitter.  For misaligned address crossing cache line boundary

from nmigen import Elaboratable, Module, Signal, Record, Array
from nmutil.latch import SRLatch, latchregister
from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from soc.scoreboard.addr_match import LenExpand
#from nmutil.queue import Queue

class LDData(Record):
    def __init__(self, dwidth, name=None):
        Record.__init__(self, (('err', 1), ('data', dwidth)), name=name)


class LDLatch(Elaboratable):

    def __init__(self, dwidth, awidth, mlen):
        self.addr_i = Signal(awidth, reset_less=True)
        self.mask_i = Signal(mlen, reset_less=True)
        self.valid_i = Signal(reset_less=True)
        self.ld_i = LDData(dwidth, "ld_i")
        self.ld_o = LDData(dwidth, "ld_o")
        self.valid_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.in_l = in_l = SRLatch(sync=False, name="in_l")

        comb += self.valid_o.eq(in_l.q & self.valid_i)
        latchregister(m, self.ld_i, self.ld_o, in_l.q & self.valid_o, "ld_i_r")

        return m


class LDSTSplitter(Elaboratable):

    def __init__(self, dwidth, awidth, dlen):
        self.dwidth, self.awidth, self.dlen = dwidth, awidth, dlen
        self.addr_i = Signal(awidth, reset_less=True)
        self.len_i = Signal(dlen, reset_less=True)
        self.is_ld_i = Signal(reset_less=True)
        self.ld_data_o = LDData(dwidth, "ld_data_o")
        self.ld_valid_i = Signal(reset_less=True)
        self.valid_o = Signal(2, reset_less=True)
        self.ld_data_i = Array((LDData(dwidth, "ld_data_i1"),
                                LDData(dwidth, "ld_data_i2")))

        #self.is_st_i = Signal(reset_less=True)
        #self.st_data_i = Signal(dwidth, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        dlen = self.dlen
        mlen = 1 << dlen
        m.submodules.ld1 = ld1 = LDLatch(self.dwidth, self.awidth-dlen, mlen)
        m.submodules.ld2 = ld2 = LDLatch(self.dwidth, self.awidth-dlen, mlen)
        m.submodules.lenexp = lenexp = LenExpand(self.dlen)

        # set up len-expander, len to mask.  ld1 gets first bit, ld2 gets rest
        comb += lenexp.addr_i.eq(self.addr_i)
        comb += lenexp.len_i.eq(self.len_i)
        mask1 = lenexp.lexp_o[0:mlen] # Lo bits of expanded len-mask
        mask2 = lenexp.lexp_o[mlen:]  # Hi bits of expanded len-mask

        # set up new address records: addr1 is "as-is", addr2 is +1
        comb += ld1.addr_i.eq(self.addr_i[dlen:])
        comb += ld2.addr_i.eq(self.addr_i[dlen:] + 1) # TODO exception if rolls

        # set up connections to LD-split.  note: not active if mask is zero
        for i, (ld, mask) in enumerate(((ld1, mask1),
                                        (ld2, mask2))):
            comb += ld.valid_i.eq(self.ld_valid_i)
            comb += ld.ld_i.eq(self.ld_data_i[i])
            comb += self.valid_o[i].eq(ld.valid_o & (mask != 0))

        # all bits valid (including when a data error occurs!) decode ld1/ld2
        with m.If(self.valid_o.all()):
            # errors cause error condition
            comb += self.ld_data_o.err.eq(ld1.ld_o.err | ld2.ld_o.err)
            # data needs recombining via shifting.
            ashift1 = self.addr_i[:self.dlen]
            # note that data from LD1 will be in *cache-line* byte position
            # likewise from LD2 but we *know* it is at the start of the line
            comb += self.ld_data_o.data.eq((ld1.ld_o.data >> ashift1) |
                                           (ld2.ld_o.data << (1<<self.dlen)))

        return m

    def __iter__(self):
        yield self.addr_i
        yield self.len_i
        yield self.is_ld_i
        yield self.ld_data_o.err
        yield self.ld_data_o.data
        yield self.ld_valid_i
        yield self.valid_o
        for i in range(2):
            yield self.ld_data_i[i].err
            yield self.ld_data_i[i].data

    def ports(self):
        return list(self)


if __name__ == '__main__':
    dut = LDSTSplitter(32, 48, 3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("ldst_splitter.il", "w") as f:
        f.write(vl)

