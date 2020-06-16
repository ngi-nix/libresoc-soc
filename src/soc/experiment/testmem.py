from nmigen import Module, Elaboratable, Memory


class TestMemory(Elaboratable):
    def __init__(self, regwid, addrw, granularity=None):
        self.ddepth = 1 # regwid //8
        depth = (1<<addrw) // self.ddepth
        self.depth = depth
        self.regwid = regwid
        self.mem   = Memory(width=regwid, depth=depth,
                            init=range(0, depth*2, 2))
        self.rdport = self.mem.read_port() # not now transparent=False)
        self.wrport = self.mem.write_port(granularity=granularity)

    def elaborate(self, platform):
        m = Module()
        m.submodules.rdport = self.rdport
        m.submodules.wrport = self.wrport
        return m

    def __iter__(self):
        yield self.rdport.addr
        yield self.rdport.data
        yield self.rdport.en
        yield self.wrport.addr
        yield self.wrport.data
        yield self.wrport.en

    def ports(self):
        return list(self)
