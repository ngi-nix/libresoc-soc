from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Elaboratable, Array
from nmutil.iocontrol import RecordObject

from nmutil.latch import SRLatch, latchregister
from soc.decoder.power_decoder2 import Data
from soc.decoder.power_enums import InternalOp

from soc.experiment.compldst import CompLDSTOpSubset
from soc.decoder.power_decode2 import Data


class PortInterface(RecordObject):

    def __init__(self, name=None):

        RecordObject.__init__(self, name=name)

        # distinguish op type (ld/st)
        self.is_ld_i = Signal(reset_less=True)
        self.is_st_i = Signal(reset_less=True)
        self.op = CompLDSTOpSubset() # hm insn_type ld/st duplicates here

        # common signals
        self.busy_o = Signal(reset_less=True)     # do not use if busy
        self.go_die_i = Signal(reset_less=True)   # back to reset
        self.addr = Data(48, "addr_i")            # addr/addr-ok
        self.addr_ok_o = Signal(reset_less=True)  # addr is valid (TLB, L1 etc.)
        self.addr_exc_o = Signal(reset_less=True) # TODO, "type" of exception

        # LD/ST
        self.ld = Data(64, "ld_data_o") # ok to be set by L0 Cache/Buf
        self.st = Data(64, "st_data_i") # ok to be set by CompUnit


class L0CacheBuffer(Elaboratable):
    """L0 Cache / Buffer

    Note that the final version will have *two* interfaces per LDSTCompUnit,
    to cover mis-aligned requests.
    """

    def __init__(self, n_units):
        self.n_units = n_units
        ul = []
        for i in range(n_units):
            ul.append(PortInterface("ldst_port%d" % i))
        self.ports = Array(ul)


def test_l0_cache():
    from alu_hier import ALU

    alu = ALU(16)
    dut = ComputationUnitNoDelay(16, alu)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compalu.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut), vcd_name='test_compalu.vcd')


if __name__ == '__main__':
    test_l0_cache()
