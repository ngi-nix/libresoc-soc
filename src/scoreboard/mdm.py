from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module

from scoreboard.fu_reg_matrix import FURegDepMatrix
from scoreboard.addr_match import PartialAddrMatch

class FUMemMatchMatrix(FURegDepMatrix, PartialAddrMatch):
    """ implement a FU-Regs overload with memory-address matching
    """
    def __init__(self, n_fu, addrbitwid):
        PartialAddrMatch.__init__(self, n_fu, addrbitwid)
        FURegDepMatrix.__init__(self, n_fu, n_fu, 1, self.addr_match_o)

    def elaborate(self, platform):
        m = Module()
        PartialAddrMatch._elaborate(self, m, platform)
        FURegDepMatrix._elaborate(self, m, platform)

        return m


