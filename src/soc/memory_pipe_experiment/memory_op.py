import enum
from nmutil.iocontrol import Object
from nmigen import Signal
from .config import MemoryPipeConfig


class MemoryOpKind(enum.IntEnum):
    Fence = enum.auto()
    Read = enum.auto()
    Write = enum.auto()
    AMO = enum.auto()
    LoadLinked = enum.auto()
    StoreConditional = enum.auto()


class MemoryOpData(Object):
    def __init__(self, config: MemoryPipeConfig):
        self.config = config
        Object.__init__(self)
        self.kind = Signal(MemoryOpKind)
        self.is_cachable = Signal()
        self.blocks_combining_with_earlier_reads = Signal()
        self.blocks_combining_with_earlier_writes = Signal()
        self.blocks_combining_with_later_reads = Signal()
        self.blocks_combining_with_later_writes = Signal()
        self.is_speculative = Signal()
        self.physical_address = Signal(config.physical_address_bits)
        self.byte_mask = Signal(config.bytes_per_cache_line)
        self.fu_op_id = Signal(config.fu_op_id_shape,
                               reset=self.config.fu_op_id_nop_value)

    @property
    def is_empty(self):
        self.fu_op_id == self.config.fu_op_id_nop_value

    def eq_empty(self):
        """ assign self to the canonical empty value. """
        return self.eq(MemoryOpData(self.config))
