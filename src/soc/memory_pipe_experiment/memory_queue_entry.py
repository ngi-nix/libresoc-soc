from nmigen import Elaboratable, Module, Signal
from .config import MemoryPipeConfig
from .memory_op import MemoryOpData


class MemoryQueueEntryComb(Elaboratable):
    """ Combinatorial state calculation for a memory queue entry, without shifting. """

    def __init__(self, config: MemoryPipeConfig):
        self.config = config
        self.op = MemoryOpData(config)
        self.op_out = MemoryOpData(config)

    def elaborate(self, platform):
        m = Module()

        kind = self.op.kind
        is_cachable = self.op.is_cachable
        is_acquire_operation = self.op.is_acquire_operation
        is_release_operation = self.op.is_release_operation
        is_speculative = self.op.is_speculative
        physical_address = self.op.physical_address
        byte_mask = self.op.byte_mask
        fu_op_id = self.op.fu_op_id

        # FIXME(programmerjake): wire up actual operations

        m.d.comb += self.op_out.kind.eq(kind)
        m.d.comb += self.op_out.is_cachable.eq(is_cachable)
        m.d.comb += self.op_out.is_acquire_operation.eq(is_acquire_operation)
        m.d.comb += self.op_out.is_release_operation.eq(is_release_operation)
        m.d.comb += self.op_out.is_speculative.eq(is_speculative)
        m.d.comb += self.op_out.physical_address.eq(physical_address)
        m.d.comb += self.op_out.byte_mask.eq(byte_mask)
        m.d.comb += self.op_out.fu_op_id.eq(fu_op_id)
        return m


class MemoryQueueEntry(Elaboratable):
    def __init__(self, config: MemoryPipeConfig):
        self.config = config
        self.op = MemoryOpData(config)
        self.next_op = MemoryOpData(config)

        """ `next_op` of corresponding memory queue entry in the next chunk towards the back of the queue. """
        self.next_back_chunks_next_op = MemoryOpData(config)
        self.do_shift = Signal()
        self.entry_comb = MemoryQueueEntryComb(config)

    def elaborate(self, platform):
        m = Module()
        m.submodules.entry_comb = self.entry_comb
        m.d.comb += self.entry_comb.op.eq(self.op)
        m.d.comb += self.next_op.eq(self.entry_comb.op_out)
        with m.If(self.do_shift):
            m.d.sync += self.op.eq(self.next_back_chunks_next_op)
        with m.Else():
            m.d.sync += self.op.eq(self.next_op)
        return m
