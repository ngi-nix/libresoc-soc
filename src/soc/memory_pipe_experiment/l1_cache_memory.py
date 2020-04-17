from nmigen import Elaboratable, Signal, Module, Mux, Repl, Array
from nmigen.hdl.mem import ReadPort, WritePort, Memory
from .config import MemoryPipeConfig


class L1CacheMemory(Elaboratable):
    """ The data memory for the L1 cache.

    It is conceptually organized into `config.l1_way_count` ways,
    where each way has `config.l1_sets_count` sets,
    where each set is a single cache line of `config.bytes_per_cache_line`
    bytes. None of the dimensions must be powers of 2, but must all be at
    least 1.

    The memory has a single R/W port that can read or write
    (but not both) an entire cache line each cycle.
    When writing, writing to each byte can individually be enabled by setting
    the corresponding bit in `write_byte_en`.

    The results of reading are available after the next clock edge.

    The address is divided into `set_index` and `way_index`.

    Parameters:

    config: MemoryPipeConfig
        The configuration.

    Attributes:

    config: MemoryPipeConfig
        The configuration.
    set_index: Signal(range(config.l1_set_count))
        The input index of the set to read/write.
    way_index: Signal(range(config.l1_way_count))
        The input index of the way to read/write.
    write_byte_en: Signal(config.bytes_per_cache_line)
        The per-byte write enable inputs.
    write_enable: Signal()
        The overall write enable input.
        Set to 1 to write and to 0 to read.
    read_data: Signal(config.bits_per_cache_line)
        The read data output.
    write_data: Signal(config.bits_per_cache_line)
        The write data input.

    """

    def __init__(self, config: MemoryPipeConfig):
        self.config = config
        self.set_index = Signal(range(config.l1_set_count), reset_less=True)
        self.way_index = Signal(range(config.l1_way_count),
                                reset_less=True)
        self.write_byte_en = Signal(config.bytes_per_cache_line,
                                    reset_less=True)
        self.write_enable = Signal(reset_less=True)
        self.read_data = Signal(config.bits_per_cache_line,
                                reset_less=True)
        self.write_data = Signal(config.bits_per_cache_line,
                                 reset_less=True)

    def elaborate(self, platform):
        m = Module()
        read_data_signals = []
        for way in range(self.config.l1_way_count):
            way_memory_name = f"way_memory_{way}"
            way_memory = Memory(width=self.config.bits_per_cache_line,
                                depth=self.config.l1_set_count,
                                name=way_memory_name)
            write_port = WritePort(way_memory, granularity=8)
            setattr(m.submodules, way_memory_name + '_write_port', write_port)
            m.d.comb += write_port.addr.eq(self.set_index)
            m.d.comb += write_port.data.eq(self.write_data)
            way_enable = Signal(name=f"way_enable_{way}", reset_less=True)
            m.d.comb += way_enable.eq(way == self.way_index)
            way_write_enable = self.write_enable & way_enable
            way_read_enable = ~self.write_enable & way_enable
            m.d.comb += write_port.en.eq(
                Repl(way_write_enable,
                     self.config.bytes_per_cache_line
                     ) & self.write_byte_en)
            read_port = ReadPort(way_memory, transparent=False)
            setattr(m.submodules, way_memory_name + '_read_port', read_port)
            m.d.comb += read_port.addr.eq(self.set_index)
            m.d.comb += read_port.en.eq(way_read_enable)
            read_data_signals.append(read_port.data)

        last_way_index = Signal.like(self.way_index)
        m.d.sync += last_way_index.eq(self.way_index)
        read_data = Array(read_data_signals)
        m.d.comb += self.read_data.eq(read_data[last_way_index])
        return m
