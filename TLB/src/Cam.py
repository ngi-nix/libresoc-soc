from nmigen import Array, Module, Signal
from nmigen.lib.coding import Encoder, Decoder
from nmigen.cli import main #, verilog

from CamEntry import CamEntry

class Cam():
    """ Content Addressable Memory (CAM)

        The purpose of this module is to quickly look up whether an
        entry exists given a certain key and return the mapped data.
        This module when given a key will search for the given key
        in all internal entries and output whether a match was found or not.
        If an entry is found the data will be returned and data_hit is HIGH,
        if it is not LOW is asserted on data_hit. When given a write
        command it will write the given key and data into the given cam
        entry index.
        Entry managment should be performed one level above this block
        as lookup is performed within.

        Notes:
        The search, write, and reset operations take one clock cycle
        to complete.  Performing a read immediately after a search will cause
        the read to be ignored.
    """

    def __init__(self, data_size, cam_size):
        """ Arguments:
            * data_size: (bit count) The size of the data
            * cam_size: (entry count) The number of entries int he CAM
        """

        # Internal
        self.cam_size = cam_size
        self.encoder = Encoder(cam_size)
        self.decoder = Decoder(cam_size)
        self.entry_array = Array(CamEntry(data_size) \
                            for x in range(cam_size))

        # Input
        # 000 => NA 001 => Read 010 => Write 011 => Search
        # 100 => Reset 101, 110, 111 => Reserved
        self.command = Signal(3) 
        self.enable = Signal(1)
        self.data_in = Signal(data_size) # The data to be written
        self.data_mask = Signal(data_size) # mask for ternary writes
        self.write_enable = Signal(1) # write
        self.address = Signal(max=cam_size) # address of CAM Entry to write/read
        
        # Output
        self.data_hit = Signal(1) # Denotes a key data pair was stored at key_in
        self.data_out = Signal(data_size) # The data mapped to by key_in

    def elaborate(self, platform=None):
        m = Module()
        # Encoder is used to selecting what data is output when searching
        m.submodules += self.encoder
        # Decoder is used to select which entry will be written to
        m.submodules += self.decoder
        # Don't forget to add all entries to the submodule list
        entry_array = self.entry_array
        m.submodules += entry_array

        # Decoder logic
        m.d.comb += [
            self.decoder.i.eq(self.address),
            self.decoder.n.eq(0)
        ]

        # Set the key value for every CamEntry
        for index in range(self.cam_size):
            with m.Switch(self.command):
                # Read from a single entry
                with m.Case("0-1"):
                    m.d.comb += entry_array[index].command.eq(1)
                    # Only read if an encoder value is not ready
                    with m.If(self.decoder.o[index] & self.encoder.n):
                        m.d.comb += self.data_out.eq(entry_array[index].data)
                # Write only to one entry
                with m.Case("010"):
                    # Address is decoded and selects which
                    # entry will be written to
                    with m.If(self.decoder.o[index]):
                        m.d.comb += entry_array[index].command.eq(2)
                    with m.Else():
                        m.d.comb += entry_array[index].command.eq(0)
                # Search all entries
                with m.Case("011"):
                    m.d.comb += entry_array[index].command.eq(1)
                # Reset
                with m.Case("100"):
                    m.d.comb += entry_array[index].command.eq(3)
                # NA / Reserved
                with m.Case():
                    m.d.comb += entry_array[index].command.eq(0)

            m.d.comb += [
                   entry_array[index].data_in.eq(self.data_in),
                   self.encoder.i[index].eq(entry_array[index].match)
            ]

        # Process out data based on encoder address
        with m.If(self.encoder.n == 0):
            m.d.comb += [
                self.data_hit.eq(1),
                self.data_out.eq(entry_array[self.encoder.o].data)
            ]
        with m.Else():
            m.d.comb += self.data_hit.eq(0)

        return m

if __name__ == '__main__':
    cam = Cam(4, 4)
    main(cam, ports=[cam.command, cam.address,
                     cam.data_in, cam.data_hit,
                     cam.data_out])

