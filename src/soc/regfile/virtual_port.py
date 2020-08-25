"""VirtualRegPort - terrible name for a complex register class

This Register file has a "virtual" port on it which is effectively
the ability to read and write to absolutely every bit in the regfile
at once.  This is achieved by having N actual read and write ports
if there are N registers.  That results in a staggeringly high gate count
with full crossbars, so attempting to do use this for anything other
than really small registers (XER, CR) is a seriously bad idea.
"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from nmigen import Cat, Const, Array, Signal, Elaboratable, Module
from nmutil.iocontrol import RecordObject

from soc.regfile.regfile import RegFileArray


class VirtualRegPort(RegFileArray):
    def __init__(self, bitwidth, n_regs, rd2=False):
        self.bitwidth = bitwidth
        self.nregs = n_regs
        self.rd2 = rd2 # eurgh hack
        self.regwidth = regwidth = bitwidth // n_regs
        super().__init__(self.regwidth, n_regs)

        # "full" depth variant of the "external" port
        self.full_wr = RecordObject([("wen", n_regs),
                                     ("data_i", bitwidth)],  # *full* wid
                                    name="full_wr")
        self.full_rd = RecordObject([("ren", n_regs),
                                     ("data_o", bitwidth)],  # *full* wid
                                    name="full_rd")
        if not rd2:
            return
        self.full_rd2 = RecordObject([("ren", n_regs),
                                     ("data_o", bitwidth)],  # *full* wid
                                    name="full_rd2")

    def connect_full_rd(self, m, rfull, name):
        comb = m.d.comb
        rd_regs = self.read_reg_port(name)

        # wire up the enable signals and chain-accumulate the data
        l = map(lambda port: port.data_o, rd_regs)  # get port data(s)
        le = map(lambda port: port.ren, rd_regs)  # get port ren(s)

        comb += rfull.data_o.eq(Cat(*l))  # we like Cat on lists
        comb += Cat(*le).eq(rfull.ren)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb

        # for internal use only.
        wr_regs = self.write_reg_port(f"w")

        # connect up full read port
        self.connect_full_rd(m, self.full_rd, "r")
        if self.rd2: # hack!
            self.connect_full_rd(m, self.full_rd2, "r2")

        # connect up full write port
        wfull = self.full_wr

        # wire up the enable signals from the large (full) port
        l = map(lambda port: port.data_i, wr_regs)
        le = map(lambda port: port.wen, wr_regs)  # get port wen(s)

        # get list of all data_i (and wens) and assign to them via Cat
        comb += Cat(*l).eq(wfull.data_i)
        comb += Cat(*le).eq(wfull.wen)

        return m

    def __iter__(self):
        yield from super().__iter__()
        yield from self.full_wr
        yield from self.full_rd


def regfile_array_sim(dut, rp1, rp2, rp3, wp):
    # part-port write
    yield wp.data_i.eq(2)
    yield wp.wen.eq(1 << 1)
    yield
    yield wp.wen.eq(0)
    # part-port read
    yield rp1.ren.eq(1 << 1)
    yield
    data = yield rp1.data_o
    print(data)
    assert data == 2

    # simultaneous read/write - should be pass-thru
    yield rp1.ren.eq(1 << 5)
    yield rp2.ren.eq(1 << 1)
    yield wp.wen.eq(1 << 5)
    yield wp.data_i.eq(6)
    yield
    yield wp.wen.eq(0)
    yield rp1.ren.eq(0)
    yield rp2.ren.eq(0)
    data1 = yield rp1.data_o
    print(data1)
    assert data1 == 6, data1
    data2 = yield rp2.data_o
    print(data2)
    assert data2 == 2, data2
    yield
    data = yield rp1.data_o
    print(data)

    # full port read (whole reg)
    yield dut.full_rd.ren.eq(0xff)
    yield
    yield dut.full_rd.ren.eq(0)
    data = yield dut.full_rd.data_o
    print(hex(data))

    # full port read (part reg)
    yield dut.full_rd.ren.eq(0x1 << 5)
    yield
    yield dut.full_rd.ren.eq(0)
    data = yield dut.full_rd.data_o
    print(hex(data))

    # full port part-write (part masked reg)
    yield dut.full_wr.wen.eq(0x1 << 1)
    yield dut.full_wr.data_i.eq(0xe0)
    yield
    yield dut.full_wr.wen.eq(0x0)

    # full port read (whole reg)
    yield dut.full_rd.ren.eq(0xff)
    yield
    yield dut.full_rd.ren.eq(0)
    data = yield dut.full_rd.data_o
    print(hex(data))

    # full port write
    yield dut.full_wr.wen.eq(0xff)
    yield dut.full_wr.data_i.eq(0xcafeface)
    yield
    yield dut.full_wr.wen.eq(0x0)

    # full port read (whole reg)
    yield dut.full_rd.ren.eq(0xff)
    yield
    yield dut.full_rd.ren.eq(0)
    data = yield dut.full_rd.data_o
    print(hex(data))

    # part write
    yield wp.data_i.eq(2)
    yield wp.wen.eq(1 << 1)
    yield
    yield wp.wen.eq(0)
    yield rp1.ren.eq(1 << 1)
    yield
    data = yield rp1.data_o
    print(hex(data))
    assert data == 2

    # full port read (whole reg)
    yield dut.full_rd.ren.eq(0xff)
    yield
    yield dut.full_rd.ren.eq(0)
    data = yield dut.full_rd.data_o
    print(hex(data))

    # simultaneous read/write: full-write, part-write, 3x part-read
    yield rp1.ren.eq(1 << 5)
    yield rp2.ren.eq(1 << 1)
    yield rp3.ren.eq(1 << 3)
    yield wp.wen.eq(1 << 3)
    yield wp.data_i.eq(6)
    yield dut.full_wr.wen.eq((1 << 1) | (1 << 5))
    yield dut.full_wr.data_i.eq((0xa << (1*4)) | (0x3 << (5*4)))
    yield
    yield dut.full_wr.wen.eq(0)
    yield wp.wen.eq(0)
    yield rp1.ren.eq(0)
    yield rp2.ren.eq(0)
    yield rp3.ren.eq(0)
    data1 = yield rp1.data_o
    print(hex(data1))
    assert data1 == 0x3
    data2 = yield rp2.data_o
    print(hex(data2))
    assert data2 == 0xa
    data3 = yield rp3.data_o
    print(hex(data3))
    assert data3 == 0x6


def test_regfile():
    dut = VirtualRegPort(32, 8)
    rp1 = dut.read_port("read1")
    rp2 = dut.read_port("read2")
    rp3 = dut.read_port("read3")
    wp = dut.write_port("write")

    ports = dut.ports()
    print("ports", ports)
    vl = rtlil.convert(dut, ports=ports)
    with open("test_virtualregfile.il", "w") as f:
        f.write(vl)

    run_simulation(dut, regfile_array_sim(dut, rp1, rp2, rp3, wp),
                   vcd_name='test_regfile_array.vcd')


if __name__ == '__main__':
    test_regfile()
