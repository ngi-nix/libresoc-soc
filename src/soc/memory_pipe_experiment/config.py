class MemoryPipeConfig:
    def __init__(self, *,
                 bytes_per_cache_line=32,
                 l1_way_count=8,
                 l1_set_count=64,
                 fu_op_id_shape=range(32),
                 fu_op_id_nop_value=0,
                 physical_address_bits=48,
                 memory_queue_chunk_size=4,
                 memory_queue_entry_count=8):
        self.bytes_per_cache_line = bytes_per_cache_line
        self.l1_way_count = l1_way_count
        self.l1_set_count = l1_set_count
        self.fu_op_id_shape = fu_op_id_shape
        self.fu_op_id_nop_value = fu_op_id_nop_value
        self.physical_address_bits = physical_address_bits
        self.memory_queue_chunk_size = memory_queue_chunk_size
        self.memory_queue_entry_count = memory_queue_entry_count

    def memory_queue_chunk_entries_start_index(self, chunk_index):
        """ entry index of the first memory queue entry in the chunk `chunk_index`. """
        return self.memory_queue_chunk_size * chunk_index

    def memory_queue_entry_index(self, chunk_index, index_in_chunk):
        return self.memory_queue_chunk_size * chunk_index + index_in_chunk

    def memory_queue_chunk_entries_end_index(self, chunk_index):
        """ one past the end entry index for in the chunk `chunk_index`. """
        v = self.memory_queue_chunk_size * (chunk_index + 1)
        return min(v, self.memory_queue_entry_count)

    @property
    def l1_line_count(self):
        return self.l1_way_count * self.l1_set_count

    @property
    def l1_byte_count(self):
        return self.l1_line_count * self.bytes_per_cache_line

    @property
    def bits_per_cache_line(self):
        return 8 * self.bytes_per_cache_line

    @property
    def memory_queue_chunk_count(self):
        return self.memory_queue_entry_count // self.memory_queue_chunk_size
