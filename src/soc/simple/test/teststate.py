from openpower.decoder.power_enums import XER_bits


class State:
    def get_state(self):
        yield from self.get_intregs()
        yield from self.get_crregs()
        yield from self.get_xregs()
        yield from self.get_pc()


class SimState(State):
    def __init__(self, sim):
        self.sim = sim

    def get_intregs(self):
        if False:
            yield
        self.intregs = []
        for i in range(32):
            simregval = self.sim.gpr[i].asint()
            self.intregs.append(simregval)
        print("class sim int regs", list(map(hex, self.intregs)))

    def get_crregs(self):
        if False:
            yield
        self.crregs = []
        for i in range(8):
            cri = self.sim.crl[7 - i].get_range().value
            self.crregs.append(cri)
        print("class sim cr regs", list(map(hex, self.crregs)))

    def get_xregs(self):
        if False:
            yield
        self.xregs = []
        self.so = self.sim.spr['XER'][XER_bits['SO']].value
        self.ov = self.sim.spr['XER'][XER_bits['OV']].value
        self.ov32 = self.sim.spr['XER'][XER_bits['OV32']].value
        self.ca = self.sim.spr['XER'][XER_bits['CA']].value
        self.ca32 = self.sim.spr['XER'][XER_bits['CA32']].value
        self.ov = self.ov | (self.ov32 << 1)
        self.ca = self.ca | (self.ca32 << 1)
        self.xregs.extend((self.so, self.ov, self.ca))
        print("class sim xregs", list(map(hex, self.xregs)))

    def get_pc(self):
        if False:
            yield
        self.pcl = []
        self.pc = self.sim.pc.CIA.value
        self.pcl.append(self.pc)
        print("class sim pc", hex(self.pc))


class HDLState(State):
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
        print("class hdl int regs", list(map(hex, self.intregs)))

    def get_crregs(self):
        self.crregs = []
        for i in range(8):
            rval = yield self.core.regs.cr.regs[i].reg
            self.crregs.append(rval)
        print("class hdl cr regs", list(map(hex, self.crregs)))

    def get_xregs(self):
        self.xregs = []
        self.xr = self.core.regs.xer
        self.so = yield self.xr.regs[self.xr.SO].reg
        self.ov = yield self.xr.regs[self.xr.OV].reg
        self.ca = yield self.xr.regs[self.xr.CA].reg
        self.xregs.extend((self.so, self.ov, self.ca))
        print("class hdl xregs", list(map(hex, self.xregs)))

    def get_pc(self):
        self.pcl = []
        self.state = self.core.regs.state
        self.pc = yield self.state.r_ports['cia'].o_data
        self.pcl.append(self.pc)
        print("class hdl pc", hex(self.pc))


def TestState(state_type, dut, state_dic):
    state_factory = {'sim': SimState, 'hdl': HDLState}
    state_class = state_factory[state_type]
    state = state_class(state_dic[state_type])
    state.dut = dut
    state.state_type = state_type
    yield from state.get_state()
    return state
