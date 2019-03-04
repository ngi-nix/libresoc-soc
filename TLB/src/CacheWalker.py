from nmigen import Memory, Module, Signal
from nmigen.cli import main
from math import log

class CacheWalker():
    """ The purpose of this module is to search a memory block given an
        associativity.  This module will attempt to find a matching
        entry when given an address, and perform permission validation
        if successful.
    """
    def __init__(self, data_size, assoc, mem):
        """ Arguments:
            * data_size: (bit count) The size of the data words being processed
            * assoc: (int) The associativity of the memory to be parsed
            * mem: (nmigen.Memory) The memory to be parsed

            Return:
            1. An entry was found -> Return PTE, set hit HIGH, set valid HIGH
            2. An entry was NOT found -> set hit LOW, set valid HIGH
            3. A permission fault occurs -> set hit LOW, set valid LOW
        """
        # Parameter parsing
        self.assoc = assoc # Assciativity of the cache

        self.read_port = mem.read_port
        self.write_port = mem.write_port 

        if (mem_size % assoc != 0):
            print("Cache Walker: Memory cannot be distributed between sets")

        self.set_count = mem.depth / assoc # Number of sets in memory
        self.set_bit_count = log(set_count, 2) # Bit count for sets
        # Ensure set_bit_count is fully represented
        if(set_count % 2 != 0):
            set_bit_count += 1

        self.assoc_bits = Signal(set_bit_count) # Bits for associativity

        # Inputs
        self.vma = Signal(36) # Virtual Memory Address (VMA)

        # Output
        self.hit = Signal(1) # Denotes if the VMA had a mapped PTE
        self.pte = Signal(64) # PTE that was mapped to by the VMA
        self.valid = Signal(1) # Denotes if the permissions are correct
