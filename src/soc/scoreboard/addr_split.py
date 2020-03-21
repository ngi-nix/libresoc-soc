# LDST Address Splitter.  For misaligned address crossing cache line boundary

from nmigen import Elaboratable, Module, Signal, Record
from nmutil.latch import SRLatch, latchregister
from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from soc.scoreboard.addr_match import LenSplitter
from nmutil.queue import Queue


class LDQueue(Elaboratable):

    def __init__(self, dwidth, awidth, mlen):
        self.addr_i = Signal(awidth, reset_less=True)
        self.mask_i = Signal(mlen, reset_less=True)
        self.ld_i = Record((('err', 1), ('data', dwidth))
        self.ld_o = Record((('err', 1), ('data', dwidth))

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.q = q = Queue(width=self.ld_o.shape()[0], 1, fwft=True)


class LDSTSplitter(Elaboratable):

    def __init__(self, dwidth, awidth, dlen):
        self.addr_i = Signal(awidth, reset_less=True)
        self.len_i = Signal(dlen, reset_less=True)
        self.is_ld_i = Signal(reset_less=True)
        self.ld_data_o = Signal(dwidth, reset_less=True)

        self.is_st_i = Signal(reset_less=True)
        self.st_data_i = Signal(dwidth, reset_less=True)
