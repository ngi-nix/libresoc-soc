from nmigen import Array, Module, Signal
from nmigen.lib.coding import Encoder
from nmigen.cli import main

from math import log

from CamEntry import CamEntry

class CAM():
    def __init__(self, key_size, data_size, cam_size):
        # Internal
        entry_array = Array(CamEntry(key_size, data_size) for x in range(cam_size))
        encoder_input = Signal(cam_size)
        
        # Input
        self.write = Signal(1)
        self.key = Signal(key_size)
        self.data_in = Signal(key_size)
        
        # Output
        self.data_match = Signal(1)
        self.data_out = Signal(data_size)
        
        def elaborate(self, platform):
            m = Module()
            
            m.d.submodules.encoder = encoder = Encoder(cam_size)
              
            for index in range(cam_size):
                m.d.sync += [
                    entry_array[index].write.eq(self.write),
                    entry_array[index].key_in.eq(self.key),
                    entry_array[index].data_in.eq(self.data_in),
                    encoder_input[index].eq(entry_array[index].match)
                ]
            
            
            m.d.sync += [
                encoder.i.eq(encoder_input),
                #  1. Read request
                #  2. Write request
                If(self.write == 0,
                   # 0 denotes a mapping was found
                   If(encoder.n == 0,
                      self.data_match.eq(0),
                      self.data_out.eq(entry_array[encoder.o].data)                      
                    ).Else(
                       self.data_match.eq(1) 
                    )
                ).Else(
                    # 0 denotes a mapping was found
                    If(encoder.n == 0,
                       self.data_match.eq(0),
                       entry_array[encoder.o].data_in.eq(self.data_in)                       
                    ).Else(
                        # LRU algorithm here
                    )
                )
                
            ]
                
            return m
            