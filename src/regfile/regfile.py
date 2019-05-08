from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from nmigen import Cat, Const, Array, Signal, Elaboratable, Module
from nmutil.iocontrol import RecordObject

from math import log
from functools import reduce
import operator


class Register(Elaboratable):
    def __init__(self, width):
        self.width = width
        self._rdports = []
        self._wrports = []

    def read_port(self, name=None):
        port = RecordObject([("ren", 1),
                             ("data_o", self.width)],
                            name=name)
        self._rdports.append(port)
        return port

    def write_port(self, name=None):
        port = RecordObject([("wen", 1),
                             ("data_i", self.width)],
                            name=name)
        self._wrports.append(port)
        return port

    def elaborate(self, platform):
        m = Module()
        self.reg = reg = Signal(self.width, name="reg")

        # read ports. has write-through detection (returns data written)
        for rp in self._rdports:
            wr_detect = Signal(reset_less=False)
            with m.If(rp.ren):
                m.d.comb += wr_detect.eq(0)
                for wp in self._wrports:
                    with m.If(wp.wen):
                        m.d.comb += rp.data_o.eq(wp.data_i)
                        m.d.comb += wr_detect.eq(1)
                with m.If(~wr_detect):
                    m.d.comb += rp.data_o.eq(reg)

        # write ports, don't allow write to address 0 (ignore it)
        for wp in self._wrports:
            with m.If(wp.wen):
                m.d.sync += reg.eq(wp.data_i)

        return m

    def __iter__(self):
        for p in self._rdports:
            yield from p
        for p in self._wrports:
            yield from p

    def ports(self):
        res = list(self)

def treereduce(tree):
    #print ("treereduce", tree)
    if not isinstance(tree, list):
        return tree
    if len(tree) == 1:
        return tree[0].data_o
    if len(tree) == 2:
        return tree[0].data_o | tree[1].data_o
    splitpoint = len(tree) // 2
    return treereduce(tree[:splitpoint]) | treereduce(tree[splitpoint:])


class RegFileArray(Elaboratable):
    """ an array-based register file (register having write-through capability)
        that has no "address" decoder, instead it has individual write-en
        and read-en signals (per port).
    """
    def __init__(self, width, depth):
        self.width = width
        self.depth = depth
        self.regs = Array(Register(width) for _ in range(self.depth))
        self._rdports = []
        self._wrports = []

    def read_port(self, name=None):
        regs = []
        for i in range(self.depth):
            port = self.regs[i].read_port(name)
            regs.append(port)
        regs = Array(regs)
        port = RecordObject([("ren", self.depth),
                             ("data_o", self.width)], name)
        self._rdports.append((regs, port))
        return port

    def write_port(self, name=None):
        regs = []
        for i in range(self.depth):
            port = self.regs[i].write_port(name)
            regs.append(port)
        regs = Array(regs)
        port = RecordObject([("wen", self.depth),
                             ("data_i", self.width)])
        self._wrports.append((regs, port))
        return port

    def _get_en_sig(self, port, typ):
        wen = []
        for p in port:
            wen.append(p[typ])
        return Cat(*wen)

    def elaborate(self, platform):
        m = Module()
        for i, reg in enumerate(self.regs):
            setattr(m.submodules, "reg_%d" % i, reg)

        for (regs, p) in self._rdports:
            #print (p)
            m.d.comb += self._get_en_sig(regs, 'ren').eq(p.ren)
            ror = treereduce(list(regs))
            m.d.comb += p.data_o.eq(ror)
        for (regs, p) in self._wrports:
            m.d.comb += self._get_en_sig(regs, 'wen').eq(p.wen)
            for r in regs:
                m.d.comb += r.data_i.eq(p.data_i)

        return m

    def __iter__(self):
        for r in self.regs:
            yield from r

    def ports(self):
        return list(self)


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

def regfile_array_sim(dut, rp1, rp2, wp):
    yield wp.data_i.eq(2)
    yield wp.wen.eq(1<<1)
    yield
    yield wp.wen.eq(0)
    yield rp1.ren.eq(1<<1)
    yield
    data = yield rp1.data_o
    print (data)
    assert data == 2

    yield rp1.ren.eq(1<<5)
    yield rp2.ren.eq(1<<1)
    yield wp.wen.eq(1<<5)
    yield wp.data_i.eq(6)
    data = yield rp1.data_o
    print (data)
    yield
    yield wp.wen.eq(0)
    yield rp1.ren.eq(0)
    yield rp2.ren.eq(0)
    data1 = yield rp1.data_o
    print (data1)
    data2 = yield rp2.data_o
    print (data2)
    assert data1 == 6
    yield
    data = yield rp1.data_o
    print (data)

def test_regfile():
    dut = RegFile(32, 8)
    rp = dut.read_port()
    wp = dut.write_port()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_regfile.il", "w") as f:
        f.write(vl)

    run_simulation(dut, regfile_sim(dut, rp, wp), vcd_name='test_regfile.vcd')

    dut = RegFileArray(32, 8)
    rp1 = dut.read_port("read1")
    rp2 = dut.read_port("read2")
    wp = dut.write_port("write")
    ports=dut.ports()
    print ("ports", ports)
    vl = rtlil.convert(dut, ports=ports)
    with open("test_regfile_array.il", "w") as f:
        f.write(vl)

    run_simulation(dut, regfile_array_sim(dut, rp1, rp2, wp),
                   vcd_name='test_regfile_array.vcd')

if __name__ == '__main__':
    test_regfile()
