from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from nmigen import Cat, Const, Array, Signal, Elaboratable, Module
from nmutil.iocontrol import RecordObject

from soc.regfile import RegFileArray


class VirtualPort(RegFileArray):
    def __init__(self, bitwidth, n_regs):
        self.bitwidth = bitwidth
        self.nregs = n_regs
        self.regwidth = bitwidth / n_regs
        self.w_ports = [ self.write_port(f"{i}") for i in range(n_regs) ]
        self.r_ports = [ self.read_port(f"{i}") for i in range(n_regs) ]
        self.extra_wr.append(RecordObject([("ren", nregs), ("data_o", bitwidth, name="extra")]))
        self.extra_rd.append(RecordObject([("ren", nregs), ("data_o", bitwidth, name="extra")]))

    def elaborate(self, platform):
        m = Module()
        with m.If(self._get_en_sig(extra, "ren") == 0)
            pass
        with m.Else()
            "send data through the corresponding lower indexed ports"
