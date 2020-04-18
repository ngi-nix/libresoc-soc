from nmigen import Elaboratable, Signal, Module, Mux, Repl, Array
from .config import MemoryPipeConfig
from .l1_cache_memory import L1CacheMemory


class MemoryPipe(Elaboratable):
    def __init__(self, config: MemoryPipeConfig):
        self.config = config
        self.l1_cache_memory = L1CacheMemory(config)
        # FIXME(programmerjake): add MemoryQueue as submodule and wire everything up

    def elaborate(self, platform):
        m = Module()
        m.submodules.l1_cache_memory = self.l1_cache_memory
        return m
