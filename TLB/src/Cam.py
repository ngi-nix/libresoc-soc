from nmigen import Array, Module, Signal
from nmigen.lib.coding import PriorityEncoder, Decoder
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
        self.encoder = PriorityEncoder(cam_size)
        self.decoder = Decoder(cam_size)
        self.entry_array = Array(CamEntry(data_size) \
                            for x in range(cam_size))

        # Input
        self.enable = Signal(1)
        self.write_enable = Signal(1) 
        self.data_in = Signal(data_size) # The data to be written
        self.data_mask = Signal(data_size) # mask for ternary writes
        self.address_in = Signal(max=cam_size) # address of CAM Entry to write
        
        # Output
        self.read_warning = Signal(1) # High when a read interrupts a write
        self.single_match = Signal(1) # High when there is only one match
        self.multiple_match = Signal(1) # High when there at least two matches
        self.match_address = Signal(max=cam_size) # The lowest address matched

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
            self.decoder.i.eq(self.address_in),
            self.decoder.n.eq(0)
        ]

        # Set the key value for every CamEntry
        for index in range(self.cam_size):
            with m.If(self.enable == 1):
                
                # Read Operation
                with m.If(self.write_enable == 0):
                    m.d.comb += entry_array[index].command.eq(1)
                    
                # Write Operation
                with m.Else():
                    with m.If(self.decoder.o[index]):
                        m.d.comb += entry_array[index].command.eq(2)
                    with m.Else():
                        m.d.comb += entry_array[index].command.eq(0)
                        
                # Send data input to all entries
                m.d.comb += entry_array[index].data_in.eq(self.data_in)
                # Send all entry matches to the priority encoder
                m.d.comb += self.encoder.i[index].eq(entry_array[index].match)
                
                # Process out data based on encoder address
                with m.If(self.encoder.n == 0):
                    m.d.comb += [
                        self.single_match.eq(1),
                        self.match_address.eq(self.encoder.o)
                    ]
                with m.Else():
                    m.d.comb += [
                        self.read_warning.eq(0),
                        self.single_match.eq(0),
                        self.multiple_match.eq(0),
                        self.match_address.eq(0)
                    ]
                    
            with m.Else():
                m.d.comb += [
                        self.read_warning.eq(0),
                        self.single_match.eq(0),
                        self.multiple_match.eq(0),
                        self.match_address.eq(0)
                ]
        return m

if __name__ == '__main__':
    cam = Cam(4, 4)
    main(cam, ports=[cam.enable, cam.write_enable,
                     cam.data_in, cam.data_mask,
                     cam.read_warning, cam.single_match,
                     cam.multiple_match, cam.match_address])

