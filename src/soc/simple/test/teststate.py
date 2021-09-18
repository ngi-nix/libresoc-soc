""" Power ISA test API

This module implements the creation, inspection and comparison
of test states for TestIssuer HDL

"""

from openpower.decoder.power_enums import XER_bits
from openpower.util import log
from openpower.test.state import (State, state_add, state_factory,
                                  TestState,)


class HDLState(State):
    def __init__(self, core):
        super().__init__()
        self.core = core

    def get_intregs(self):
        self.intregs = []
        for i in range(32):
            if self.core.regs.int.unary:
                rval = yield self.core.regs.int.regs[i].reg
            else:
                rval = yield self.core.regs.int.memory._array[i]
            self.intregs.append(rval)
        log("class hdl int regs", list(map(hex, self.intregs)))

    def get_crregs(self):
        self.crregs = []
        for i in range(8):
            rval = yield self.core.regs.cr.regs[i].reg
            self.crregs.append(rval)
        log("class hdl cr regs", list(map(hex, self.crregs)))

    def get_xregs(self):
        self.xregs = []
        self.xr = self.core.regs.xer
        self.so = yield self.xr.regs[self.xr.SO].reg
        self.ov = yield self.xr.regs[self.xr.OV].reg
        self.ca = yield self.xr.regs[self.xr.CA].reg
        self.xregs.extend((self.so, self.ov, self.ca))
        log("class hdl xregs", list(map(hex, self.xregs)))

    def get_pc(self):
        self.pcl = []
        self.state = self.core.regs.state
        self.pc = yield self.state.r_ports['cia'].o_data
        self.pcl.append(self.pc)
        log("class hdl pc", hex(self.pc))

    def get_mem(self):
        if hasattr(self.core.l0.pimem, 'lsui'):
            hdlmem = self.core.l0.pimem.lsui.mem
        else:
            hdlmem = self.core.l0.pimem.mem
            if not isinstance(hdlmem, Memory):
                hdlmem = hdlmem.mem
        self.mem = []
        for i in range(hdlmem.depth):
            value = yield hdlmem._array[i]
            self.mem.append(((i*8), value))


# add to State Factory
state_add('hdl', HDLState)
