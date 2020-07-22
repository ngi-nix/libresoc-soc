from nmigen import Module, Elaboratable, Memory


class TestMemory(Elaboratable):
    def __init__(self, regwid, addrw, granularity=None, init=True,
                 readonly=False):
        self.readonly = readonly
        self.ddepth = 1  # regwid //8
        depth = (1 << addrw) // self.ddepth
        self.depth = depth
        self.regwid = regwid
        print("test memory width depth", regwid, depth)
        if init is True:
            init = range(0, depth*2, 2)
        else:
            init = None
        self.mem = Memory(width=regwid, depth=depth, init=init)
        self.rdport = self.mem.read_port()  # not now transparent=False)
        if self.readonly:
            return
        self.wrport = self.mem.write_port(granularity=granularity)

    def elaborate(self, platform):
        m = Module()
        m.submodules.rdport = self.rdport
        if self.readonly:
            return m
        m.submodules.wrport = self.wrport
        return m

    def __iter__(self):
        yield self.rdport.addr
        yield self.rdport.data
        # yield self.rdport.en
        if self.readonly:
            return
        yield self.wrport.addr
        yield self.wrport.data
        yield self.wrport.en

    def ports(self):
        return list(self)
