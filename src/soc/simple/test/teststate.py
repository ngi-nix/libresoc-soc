from openpower.decoder.power_enums import XER_bits


class SimState:
    def __init__(self, sim):
        self.sim = sim

    def get_intregs(self):
        self.intregs = []
        for i in range(32):
            simregval = self.sim.gpr[i].asint()
            self.intregs.append(simregval)

    def get_crregs(self):
        self.crregs = []
        for i in range(8):
            cri = self.sim.crl[7 - i].get_range().value
            self.crregs.append(cri)

    def get_xregs(self):
        self.so = self.sim.spr['XER'][XER_bits['SO']].value
        self.ov = self.sim.spr['XER'][XER_bits['OV']].value
        self.ov32 = self.sim.spr['XER'][XER_bits['OV32']].value
        self.ca = self.sim.spr['XER'][XER_bits['CA']].value
        self.ca32 = self.sim.spr['XER'][XER_bits['CA32']].value
        self.ov = self.ov | (self.ov32 << 1)
        self.ca = self.ca | (self.ca32 << 1)

    def get_pc(self):
        self.pc = self.sim.pc.CIA.value


class HDLState:
    def __init__(self, core):
        self.core = core

    def get_intregs(self):
        self.intregs = []
        for i in range(32):
            if self.core.regs.int.unary:
                rval = yield self.core.regs.int.regs[i].reg
            else:
                rval = yield self.core.regs.int.memory._array[i]
            self.intregs.append(rval)
        print("class core int regs", list(map(hex, self.intregs)))

    def get_crregs(self):
        self.crregs = []
        for i in range(8):
            rval = yield self.core.regs.cr.regs[i].reg
            self.crregs.append(rval)
        print("class core cr regs", list(map(hex, self.crregs)))

    def get_xregs(self):
        self.xregs = self.core.regs.xer
        self.so = yield self.xregs.regs[self.xregs.SO].reg
        self.ov = yield self.xregs.regs[self.xregs.OV].reg
        self.ca = yield self.xregs.regs[self.xregs.CA].reg
        print("class core xregs", list(map(hex, [self.so, self.ov, self.ca])))

    def get_pc(self):
        self.state = self.core.regs.state
        self.pc = yield self.state.r_ports['cia'].o_data
        print("class core pc", hex(self.pc))
