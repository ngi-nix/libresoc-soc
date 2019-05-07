from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from nmigen import Const, Array, Signal, Elaboratable, Module
from nmutil.iocontrol import RecordObject

from math import log


class RegFile(Elaboratable):
    def __init__(self, width, depth):
        self.width = width
        self.depth = depth
        self._rdports = []
        self._wrports = []

    def read_port(self):
        bsz = int(log(self.width) / log(2))
        port = RecordObject([("raddr", bsz),
                             ("ren", 1),
                             ("data_o", self.width)])
        self._rdports.append(port)
        return port

    def write_port(self):
        bsz = int(log(self.width) / log(2))
        port = RecordObject([("waddr", bsz),
                             ("wen", 1),
                             ("data_i", self.width)])
        self._wrports.append(port)
        return port

    def elaborate(self, platform):
        m = Module()
        bsz = int(log(self.width) / log(2))
        regs = Array(Signal(self.width, name="reg") for _ in range(self.depth))

        # read ports. has write-through detection (returns data written)
        for rp in self._rdports:
            wr_detect = Signal(reset_less=False)
            with m.If(rp.ren):
                m.d.comb += wr_detect.eq(0)
                for wp in self._wrports:
                    addrmatch = Signal(reset_less=False)
                    m.d.comb += addrmatch.eq(wp.waddr == rp.raddr)
                    with m.If(wp.wen & addrmatch):
                        m.d.comb += rp.data_o.eq(wp.data_i)
                        m.d.comb += wr_detect.eq(1)
                with m.If(~wr_detect):
                    m.d.comb += rp.data_o.eq(regs[rp.raddr])

        # write ports, don't allow write to address 0 (ignore it)
        for wp in self._wrports:
            with m.If(wp.wen & (wp.waddr != Const(0, bsz))):
                m.d.sync += regs[wp.waddr].eq(wp.data_i)

        return m

    def __iter__(self):
        yield from self._rdports
        yield from self._wrports

    def ports(self):
        res = list(self)
        for r in res:
            if isinstance(r, RecordObject):
                yield from r
            else:
                yield r

def regfile_sim(dut, rp, wp):
    yield wp.waddr.eq(1)
    yield wp.data_i.eq(2)
    yield wp.wen.eq(1)
    yield
    yield wp.wen.eq(0)
    yield rp.ren.eq(1)
    yield rp.raddr.eq(1)
    yield
    data = yield rp.data_o
    print (data)
    assert data == 2

    yield wp.waddr.eq(5)
    yield rp.raddr.eq(5)
    yield rp.ren.eq(1)
    yield wp.wen.eq(1)
    yield wp.data_i.eq(6)
    data = yield rp.data_o
    print (data)
    yield
    yield wp.wen.eq(0)
    yield rp.ren.eq(0)
    data = yield rp.data_o
    print (data)
    assert data == 6
    yield
    data = yield rp.data_o
    print (data)

def test_regfile():
    dut = RegFile(32, 8)
    rp = dut.read_port()
    wp = dut.write_port()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_regfile.il", "w") as f:
        f.write(vl)

    run_simulation(dut, regfile_sim(dut, rp, wp), vcd_name='test_regfile.vcd')

if __name__ == '__main__':
    test_regfile()
