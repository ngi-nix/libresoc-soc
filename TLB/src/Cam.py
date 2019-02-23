from nmigen import Array, Module, Signal
from nmigen.lib.coding import Encoder
from nmigen.compat.fhdl.structure import ClockDomain

from CamEntry import CamEntry

# Content Addressable Memory (CAM)
# The purpose of this module is to quickly look up whether an entry exists
# given a certain key and return the mapped data.
# This module when given a key will search for the given key
# in all internal entries and output whether a match was found or not.
# If an entry is found the data will be returned and data_hit is HIGH,
# if it is not LOW is asserted on data_hit. When given a write
# command it will write the given key and data into the given cam entry index.
# Entry managment should be performed one level above this block as lookup is 
# performed within.
class Cam():
    
    # Arguments:
    #  key_size: (bit count) The size of the key 
    #  data_size: (bit count) The size of the data 
    #  cam_size: (entry count) The number of entries int he CAM
    def __init__(self, key_size, data_size, cam_size):
        # Internal
        self.clk = ClockDomain(reset_less=True)
        self.key_size = key_size
        self.data_size = data_size
        self.cam_size = cam_size
        self.entry_array = Array(CamEntry(key_size, data_size) \
                            for x in range(cam_size))
        self.encoder_input = Signal(cam_size)

        # Input
        self.command = Signal(2) # 00 => NA 01 => Read 10 => Write 11 => Search
        self.address = Signal(max=cam_size) # address of CAM Entry to write/read
        self.key_in = Signal(key_size) # The key to search for or to be written
        self.data_in = Signal(key_size) # The data to be written

        # Output
        self.data_hit = Signal(1) # Denotes a key data pair was stored at key_in
        self.data_out = Signal(data_size) # The data mapped to by key_in

    def elaborate(self, platform=None):
        m = Module()
        
        m.submodules.encoder = encoder = Encoder(self.cam_size)
        m.submodules += self.entry_array
        
        # Set the key value for every CamEntry
        for index in range(self.cam_size):
            with m.Switch(self.command):
                # Read and Search both read from the CamEntry
                with m.Case("-1"):
                    m.d.comb += self.entry_array[index].command.eq(1)
                # Write only to one entry
                with m.Case("10"):
                    with m.If(self.address == index):
                        m.d.comb += self.entry_array[index].command.eq(2)
                    with m.Else():
                        m.d.comb += self.entry_array[index].command.eq(0)
                # NA
                with m.Case():
                    m.d.comb += self.entry_array[index].command.eq(0)
 
            m.d.comb += [
                   self.entry_array[index].key_in.eq(self.key_in),
                   self.entry_array[index].data_in.eq(self.data_in),
                   self.encoder_input[index].eq(self.entry_array[index].match)
            ]
        
        with m.Switch(self.command):
            # Read
            with m.Case("01"):
                m.d.comb += [
                    self.data_hit.eq(0),
                    self.data_out.eq(self.entry_array[self.address].data)
                ]
            # Write
            with m.Case("10"):
                m.d.comb += [
                    self.data_hit.eq(0),
                    self.entry_array[self.address].key_in.eq(self.key_in),
                    self.entry_array[self.address].data_in.eq(self.data_in)
                ]
            # Search
            with m.Case("11"):
                m.d.comb += encoder.i.eq(self.encoder_input)
                with m.If(encoder.n == 0):
                    m.d.comb += [
                        self.data_hit.eq(0),
                        self.data_out.eq(self.entry_array[encoder.o].data)                            
                    ]
                with m.Else():
                    m.d.comb += self.data_hit.eq(1)
            # NA
            with m.Case():
                m.d.comb += self.data_hit.eq(0)
                
        return m
