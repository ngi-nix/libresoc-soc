# LDST Address Splitter.  For misaligned address crossing cache line boundary
"""
Links:
* https://libre-riscv.org/3d_gpu/architecture/6600scoreboard/
* http://bugs.libre-riscv.org/show_bug.cgi?id=257
* http://bugs.libre-riscv.org/show_bug.cgi?id=216
"""

#from soc.experiment.pimem import PortInterface

from nmigen import Elaboratable, Module, Signal, Record, Array, Const, Cat
from nmutil.latch import SRLatch, latchregister
from nmigen.back.pysim import Simulator, Delay
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

        comb += in_l.s.eq(self.valid_i)
        comb += self.valid_o.eq(in_l.q & self.valid_i)
        latchregister(m, self.ld_i, self.ld_o, in_l.q & self.valid_o, "ld_i_r")

        return m

    def __iter__(self):
        yield self.addr_i
        yield self.mask_i
        yield self.ld_i.err
        yield self.ld_i.data
        yield self.ld_o.err
        yield self.ld_o.data
        yield self.valid_i
        yield self.valid_o

    def ports(self):
        return list(self)

def byteExpand(signal):
    if(type(signal)==int):
        ret = 0
        shf = 0
        while(signal>0):
            bit = signal & 1
            ret |= (0xFF * bit) << shf
            signal = signal >> 1
            shf += 8
        return ret
    lst = []
    for i in range(len(signal)):
        bit = signal[i]
        for j in range(8): #TODO this can be optimized
            lst += [bit]
    return Cat(*lst)

class LDSTSplitter(Elaboratable):

    def __init__(self, dwidth, awidth, dlen, pi=None):
        self.dwidth, self.awidth, self.dlen = dwidth, awidth, dlen
        # cline_wid = 8<<dlen # cache line width: bytes (8) times (2^^dlen)
        cline_wid = dwidth*8  # convert bytes to bits

        self.addr_i = Signal(awidth, reset_less=True)
        # no match in PortInterface
        self.len_i = Signal(dlen, reset_less=True)
        self.valid_i = Signal(reset_less=True)
        self.valid_o = Signal(reset_less=True)

        self.is_ld_i = Signal(reset_less=True)
        self.is_st_i = Signal(reset_less=True)

        self.ld_data_o = LDData(dwidth*8, "ld_data_o") #port.ld
        self.st_data_i = LDData(dwidth*8, "st_data_i") #port.st

        self.exc = Signal(reset_less=True) # pi.exc TODO
        # TODO : create/connect two outgoing port interfaces

        self.sld_valid_o = Signal(2, reset_less=True)
        self.sld_valid_i = Signal(2, reset_less=True)
        self.sld_data_i = Array((LDData(cline_wid, "ld_data_i1"),
                                 LDData(cline_wid, "ld_data_i2")))

        self.sst_valid_o = Signal(2, reset_less=True)
        self.sst_valid_i = Signal(2, reset_less=True)
        self.sst_data_o = Array((LDData(cline_wid, "st_data_i1"),
                                 LDData(cline_wid, "st_data_i2")))

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        dlen = self.dlen
        mlen = 1 << dlen
        mzero = Const(0, mlen)
        m.submodules.ld1 = ld1 = LDLatch(self.dwidth*8, self.awidth-dlen, mlen)
        m.submodules.ld2 = ld2 = LDLatch(self.dwidth*8, self.awidth-dlen, mlen)
        m.submodules.lenexp = lenexp = LenExpand(self.dlen)

        #comb += self.pi.addr_ok_o.eq(self.addr_i < 65536) #FIXME 64k limit
        #comb += self.pi.busy_o.eq(busy)


        # FIXME bytes not bits
        # set up len-expander, len to mask.  ld1 gets first bit, ld2 gets rest
        comb += lenexp.addr_i.eq(self.addr_i)
        comb += lenexp.len_i.eq(self.len_i)
        mask1 = Signal(mlen, reset_less=True)
        mask2 = Signal(mlen, reset_less=True)
        comb += mask1.eq(lenexp.lexp_o[0:mlen])  # Lo bits of expanded len-mask
        comb += mask2.eq(lenexp.lexp_o[mlen:])   # Hi bits of expanded len-mask

        # set up new address records: addr1 is "as-is", addr2 is +1
        comb += ld1.addr_i.eq(self.addr_i[dlen:])
        ld2_value = self.addr_i[dlen:] + 1
        comb += ld2.addr_i.eq(ld2_value)
        # exception if rolls
        with m.If(ld2_value[self.awidth-dlen]):
            comb += self.exc.eq(1)

        # data needs recombining / splitting via shifting.
        ashift1 = Signal(self.dlen, reset_less=True)
        ashift2 = Signal(self.dlen, reset_less=True)
        comb += ashift1.eq(self.addr_i[:self.dlen])
        comb += ashift2.eq((1 << dlen)-ashift1)

        #expand masks
        mask1 = byteExpand(mask1)
        mask2 = byteExpand(mask2)
        mzero = byteExpand(mzero)

        with m.If(self.is_ld_i):
            # set up connections to LD-split.  note: not active if mask is zero
            for i, (ld, mask) in enumerate(((ld1, mask1),
                                            (ld2, mask2))):
                ld_valid = Signal(name="ldvalid_i%d" % i, reset_less=True)
                comb += ld_valid.eq(self.valid_i & self.sld_valid_i[i])
                comb += ld.valid_i.eq(ld_valid & (mask != mzero))
                comb += ld.ld_i.eq(self.sld_data_i[i])
                comb += self.sld_valid_o[i].eq(ld.valid_o)

            # sort out valid: mask2 zero we ignore 2nd LD
            with m.If(mask2 == mzero):
                comb += self.valid_o.eq(self.sld_valid_o[0])
            with m.Else():
                comb += self.valid_o.eq(self.sld_valid_o.all())
            ## debug output -- output mask2 and mzero
            ## guess second port is invalid

            # all bits valid (including when data error occurs!) decode ld1/ld2
            with m.If(self.valid_o):
                # errors cause error condition
                comb += self.ld_data_o.err.eq(ld1.ld_o.err | ld2.ld_o.err)

                # note that data from LD1 will be in *cache-line* byte position
                # likewise from LD2 but we *know* it is at the start of the line
                comb += self.ld_data_o.data.eq((ld1.ld_o.data >> (ashift1*8)) |
                                               (ld2.ld_o.data << (ashift2*8)))

        with m.If(self.is_st_i):
            # set busy flag -- required for unit test
            for i, (ld, mask) in enumerate(((ld1, mask1),
                                            (ld2, mask2))):
                valid = Signal(name="stvalid_i%d" % i, reset_less=True)
                comb += valid.eq(self.valid_i & self.sst_valid_i[i])
                comb += ld.valid_i.eq(valid & (mask != mzero))
                comb += self.sld_valid_o[i].eq(ld.valid_o)
                comb += self.sst_data_o[i].data.eq(ld.ld_o.data)

            comb += ld1.ld_i.eq((self.st_data_i << (ashift1*8)) & mask1)
            comb += ld2.ld_i.eq((self.st_data_i >> (ashift2*8)) & mask2)

            # sort out valid: mask2 zero we ignore 2nd LD
            with m.If(mask2 == mzero):
                comb += self.valid_o.eq(self.sst_valid_o[0])
            with m.Else():
                comb += self.valid_o.eq(self.sst_valid_o.all())

            # all bits valid (including when data error occurs!) decode ld1/ld2
            with m.If(self.valid_o):
                # errors cause error condition
                comb += self.st_data_i.err.eq(ld1.ld_o.err | ld2.ld_o.err)

        return m

    def __iter__(self):
        yield self.addr_i
        yield self.len_i
        yield self.is_ld_i
        yield self.ld_data_o.err
        yield self.ld_data_o.data
        yield self.valid_i
        yield self.valid_o
        yield self.sld_valid_i
        for i in range(2):
            yield self.sld_data_i[i].err
            yield self.sld_data_i[i].data

    def ports(self):
        return list(self)


def sim(dut):

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    data = 0x0102030405060708A1A2A3A4A5A6A7A8
    dlen = 16  # data length in bytes
    addr = 0b1110
    ld_len = 8
    ldm = ((1 << ld_len)-1)
    ldme = byteExpand(ldm)
    dlm = ((1 << dlen)-1)
    data = data & ldme  # truncate data to be tested, mask to within ld len
    print("ldm", ldm, hex(data & ldme))
    print("dlm", dlm, bin(addr & dlm))

    dmask = ldm << (addr & dlm)
    print("dmask", bin(dmask))
    dmask1 = dmask >> (1 << dlen)
    print("dmask1", bin(dmask1))
    dmask = dmask & ((1 << (1 << dlen))-1)
    print("dmask", bin(dmask))
    dmask1 = byteExpand(dmask1)
    dmask = byteExpand(dmask)

    def send_ld():
        print("send_ld")
        yield dut.is_ld_i.eq(1)
        yield dut.len_i.eq(ld_len)
        yield dut.addr_i.eq(addr)
        yield dut.valid_i.eq(1)
        print("waiting")
        while True:
            valid_o = yield dut.valid_o
            if valid_o:
                break
            yield
        exc = yield dut.exc
        ld_data_o = yield dut.ld_data_o.data
        yield dut.is_ld_i.eq(0)
        yield

        print(exc)
        assert exc==0
        print(hex(ld_data_o), hex(data))
        assert ld_data_o == data

    def lds():
        print("lds")
        while True:
            valid_i = yield dut.valid_i
            if valid_i:
                break
            yield

        shf = (addr & dlm)*8  #shift bytes not bits
        print("shf",shf/8.0)
        shfdata = (data << shf)
        data1 = shfdata & dmask
        print("ld data1", hex(data), hex(data1), shf,shf/8.0, hex(dmask))

        data2 = (shfdata >> 128) & dmask1
        print("ld data2", 1 << dlen, hex(data >> (1 << dlen)), hex(data2))
        yield dut.sld_data_i[0].data.eq(data1)
        yield dut.sld_valid_i[0].eq(1)
        yield
        yield dut.sld_data_i[1].data.eq(data2)
        yield dut.sld_valid_i[1].eq(1)
        yield

    sim.add_sync_process(lds)
    sim.add_sync_process(send_ld)

    prefix = "ldst_splitter"
    with sim.write_vcd("%s.vcd" % prefix, traces=dut.ports()):
        sim.run()


if __name__ == '__main__':
    dut = LDSTSplitter(32, 48, 4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("ldst_splitter.il", "w") as f:
        f.write(vl)

    sim(dut)
