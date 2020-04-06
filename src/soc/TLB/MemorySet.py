from nmigen import Cat, Memory, Module, Signal, Elaboratable
from nmigen.cli import main
from nmigen.cli import verilog, rtlil


class MemorySet(Elaboratable):
    def __init__(self, data_size, tag_size, set_count, active):
        self.active = active
        input_size = tag_size + data_size  # Size of the input data
        memory_width = input_size + 1  # The width of the cache memory
        self.active = active
        self.data_size = data_size
        self.tag_size = tag_size

        # XXX TODO, use rd-enable and wr-enable?
        self.mem = Memory(width=memory_width, depth=set_count)
        self.r = self.mem.read_port()
        self.w = self.mem.write_port()

        # inputs (address)
        self.cset = Signal(range(set_count))  # The set to be checked
        self.tag = Signal(tag_size)        # The tag to find
        self.data_i = Signal(data_size)    # Incoming data

        # outputs
        self.valid = Signal()
        self.data_o = Signal(data_size)    # Outgoing data (excludes tag)

    def elaborate(self, platform):
        m = Module()
        m.submodules.mem = self.mem
        m.submodules.r = self.r
        m.submodules.w = self.w

        # temporaries
        active_bit = Signal()
        tag_valid = Signal()
        data_start = self.active + 1
        data_end = data_start + self.data_size
        tag_start = data_end
        tag_end = tag_start + self.tag_size

        # connect the read port address to the set/entry
        read_port = self.r
        m.d.comb += read_port.addr.eq(self.cset)
        # Pull out active bit from data
        data = read_port.data
        m.d.comb += active_bit.eq(data[self.active])
        # Validate given tag vs stored tag
        tag = data[tag_start:tag_end]
        m.d.comb += tag_valid.eq(self.tag == tag)
        # An entry is only valid if the tags match AND
        # is marked as a valid entry
        m.d.comb += self.valid.eq(tag_valid & active_bit)

        # output data: TODO, check rd-enable?
        m.d.comb += self.data_o.eq(data[data_start:data_end])

        # connect the write port addr to the set/entry (only if write enabled)
        # (which is only done on a match, see SAC.write_entry below)
        write_port = self.w
        with m.If(write_port.en):
            m.d.comb += write_port.addr.eq(self.cset)
            m.d.comb += write_port.data.eq(Cat(1, self.data_i, self.tag))

        return m
