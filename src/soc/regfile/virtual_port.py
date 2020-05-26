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
        self.regwidth = regwidth = bitwidth // n_regs
        super().__init__(self.regwidth, n_regs)

        # "full" depth variant of the "external" port
        self.full_wr = RecordObject([("wen", n_regs),
                                     ("data_i", bitwidth)], # *full* wid
                                    name="full_wr")
        self.full_rd = RecordObject([("ren", n_regs),
                                     ("data_o", bitwidth)], # *full* wid
                                    name="full_rd")
        # for internal use
        self._wr_regs = self.write_reg_port(f"intw")
        self._rd_regs = self.read_reg_port(f"intr")

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb

        # connect up: detect if read is requested on large (full) port
        # nothing fancy needed because reads are same-cycle
        rfull = self.full_rd

        # wire up the enable signals and chain-accumulate the data
        l = map(lambda port: port.data_o, self._rd_regs) # get port data(s)
        le = map(lambda port: port.ren, self._rd_regs) # get port ren(s)

        comb += rfull.data_o.eq(Cat(*l)) # we like Cat on lists
        comb += Cat(*le).eq(rfull.ren)

        # connect up: detect if write is requested on large (full) port
        # however due to the delay (1 clock) on write, we also need to
        # delay the test.  enable is not-delayed, but data is.
        wfull = self.full_wr

        # wire up the enable signals from the large (full) port
        l = map(lambda port: port.data_i, self._wr_regs)
        le = map(lambda port: port.wen, self._wr_regs) # get port wen(s)

        # get list of all data_i (and wens) and assign to them via Cat
        comb += Cat(*l).eq(wfull.data_i)
        comb += Cat(*le).eq(wfull.wen)

        return m

    def __iter__(self):
        yield from super().__iter__()
        yield from self.full_wr
        yield from self.full_rd


def test_regfile():
    dut = VirtualRegPort(32, 8)
    ports=dut.ports()
    print ("ports", ports)
    vl = rtlil.convert(dut, ports=ports)
    with open("test_virtualregfile.il", "w") as f:
        f.write(vl)

if __name__ == '__main__':
    test_regfile()

