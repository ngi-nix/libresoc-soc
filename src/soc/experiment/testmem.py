from nmigen import Module, Elaboratable, Memory


class TestMemory(Elaboratable):
    def __init__(self, regwid, addrw):
        self.ddepth = 1 # regwid //8
        depth = (1<<addrw) // self.ddepth
        self.mem   = Memory(width=regwid, depth=depth, init=range(0, depth))
        self.rdport = self.mem.read_port(transparent=False)
        self.wrport = self.mem.write_port()

    def elaborate(self, platform):
        m = Module()
        m.submodules.rdport = self.rdport
        m.submodules.wrport = self.wrport
        return m
