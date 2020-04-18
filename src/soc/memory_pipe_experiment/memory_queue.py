from nmigen import Elaboratable, Module
from .config import MemoryPipeConfig
from .memory_queue_entry import MemoryQueueEntry
from typing import Optional


class MemoryQueueChunk(Elaboratable):
    next_back_chunk: Optional["MemoryQueueChunk"]

    def __init__(self, config: MemoryPipeConfig, chunk_index: int):
        self.config = config
        self.chunk_index = chunk_index
        start = config.memory_queue_chunk_entries_start_index(chunk_index)
        end = config.memory_queue_chunk_entries_end_index(chunk_index)
        self.entries = [MemoryQueueEntry(config)
                        for i in range(start, end)]

    def elaborate(self, platform):
        m = Module()
        for i in range(len(self.entries)):
            entry = self.entries[i]
            entry_index = self.config.memory_queue_entry_index(
                self.chunk_index, i)
            setattr(m.submodules, f"entry_{entry_index}", entry)
            if self.next_back_chunk is not None and i < len(self.next_back_chunk.entries):
                m.d.comb += entry.next_back_chunks_next_op.eq(
                    self.next_back_chunk.entries[i])
            else:
                m.d.comb += entry.next_back_chunks_next_op.eq_empty()
        return m


class MemoryQueue(Elaboratable):
    def __init__(self, config: MemoryPipeConfig):
        self.config = config
        self.chunks = [MemoryQueueChunk(config, i)
                       for i in range(config.memory_queue_chunk_count)]
        self.entries = []
        for chunk in self.chunks:
            self.entries.extend(chunk.entries)

    def elaborate(self, platform):
        m = Module()
        for i in range(self.config.memory_queue_chunk_count):
            chunk = self.chunks[i]
            setattr(m.submodules, f"chunk_{i}", chunk)
            if i > 0:
                self.chunks[i - 1].next_back_chunk = chunk
        return m
