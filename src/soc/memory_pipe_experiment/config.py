class MemoryPipeConfig:
    def __init__(self, *,
                 bytes_per_cache_line=32,
                 l1_way_count=8,
                 l1_set_count=64):
        self.bytes_per_cache_line = bytes_per_cache_line
        self.l1_way_count = l1_way_count
        self.l1_set_count = l1_set_count

    @property
    def l1_line_count(self):
        return self.l1_way_count * self.l1_set_count

    @property
    def l1_byte_count(self):
        return self.l1_line_count * self.bytes_per_cache_line

    @property
    def bits_per_cache_line(self):
        return 8 * self.bytes_per_cache_line
