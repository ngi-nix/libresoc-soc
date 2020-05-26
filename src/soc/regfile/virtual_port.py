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
    def __init__(self, bitwidth, n_regs):
        self.bitwidth = bitwidth
        self.nregs = n_regs
        self.regwidth = bitwidth // n_regs
        super().__init__(self.regwidth, n_regs)

        # create suite of 8 write and 8 read ports for external use
        self.wr_ports = self.write_reg_port(f"extw")
        self.rd_ports = self.read_reg_port(f"extr")
        # now for internal use
        self._wr_regs = self.write_reg_port(f"intw")
        self._rd_regs = self.read_reg_port(f"intr")
        # and append the "full" depth variant to the "external" ports
        self.wr_ports.append(RecordObject([("wen", n_regs),
                                          ("data_i", bitwidth)], # *full* wid
                                         name="full_wr"))
        self.rd_ports.append(RecordObject([("ren", n_regs),
                                          ("data_o", bitwidth)], # *full* wid
                                         name="full_rd"))

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb, sync = m.d.comb, m.d.sync

        # connect up: detect if read is requested on large (full) port
        # nothing fancy needed because reads are same-cycle
        rlast = self.rd_ports[-1]
        print (rlast)
        with m.If(self._get_en_sig([rlast], "ren") != 0):
            # wire up the enable signals and accumulate the data
            l = []
            print (self._rdports)
            for i, port in enumerate(self._rdports[:-1]):
                print (port)
                comb += port.ren.eq(1<<i) # port indices are *unary*-indexed
                l.append(port.data_o)
            comb += rlast.data_o.eq(Cat(*l)) # we like Cat on lists
        with m.Else():
            # allow request through the corresponding lower indexed ports
            for i, port in enumerate(self._rdports[:-1]):
                comb += port.eq(self.rd_ports[i])

        # connect up: detect if write is requested on large (full) port
        # however due to the delay (1 clock) on write, we also need to
        # delay the test.  enable is not-delayed, but data is.
        en_sig = Signal(reset_less=True)   # combinatorial
        data_sig = Signal(reset_less=True) # sync (one clock delay)

        wlast = self.wr_ports[-1]
        comb += en_sig.eq(self._get_en_sig([wlast], "wen") != 0)
        sync += data_sig.eq(en_sig)

        with m.If(en_sig):
            # wire up the enable signals
            for i, port in enumerate(self._wrports[:-1]):
                comb += port.wen.eq(1<<i) # port indices are *unary*-indexed
        with m.Else():
            # allow request through the corresponding lower indexed ports
            for i, port in enumerate(self._wrports[:-1]):
                comb += port.wen.eq(self.wn_ports[i].wen)

        # and (sigh) data is on one clock-delay, connect that too
        with m.If(data_sig):
            # get list of all data_i and assign to them via Cat
            l = map(lambda port: port.data_i, self._wrports[:-1])
            comb += Cat(*l).eq(wlast.data_i)
        with m.Else():
            # allow data through the corresponding lower indexed ports
            for i, port in enumerate(self._wrports[:-1]):
                comb += self.wr_ports[i].data_i.eq(port.data_i)

        return m

    def __iter__(self):
        yield from super().__iter__()
        for p in self.wr_ports:
            yield from p
        for p in self.rd_ports:
            yield from p


def test_regfile():
    dut = VirtualRegPort(32, 4)
    ports=dut.ports()
    print ("ports", ports)
    vl = rtlil.convert(dut, ports=ports)
    with open("test_virtualregfile.il", "w") as f:
        f.write(vl)

if __name__ == '__main__':
    test_regfile()

