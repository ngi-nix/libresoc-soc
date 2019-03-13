from nmigen import Array, Module, Signal
from nmigen.lib.coding import Decoder
from nmigen.cli import main #, verilog

from CamEntry import CamEntry
from AddressEncoder import AddressEncoder
from VectorAssembler import VectorAssembler

class Cam():
    """ Content Addressable Memory (CAM)

        The purpose of this module is to quickly look up whether an
        entry exists given a data key.
        This module will search for the given data in all internal entries
        and output whether a  single or multiple match was found.
        If an single entry is found the address be returned and single_match
        is set HIGH. If multiple entries are found the lowest address is
        returned and multiple_match is set HIGH. If neither single_match or
        multiple_match are HIGH this implies no match was found. To write
        to the CAM set the address bus to the desired entry and set write_enable
        HIGH. Entry managment should be performed one level above this block
        as lookup is performed within.

        Notes:
        The read and write operations take one clock cycle to complete.
        Currently the read_warning line is present for interfacing but
        is not necessary for this design. This module is capable of writing
        in the first cycle, reading on the second, and output the correct
        address on the third.
    """

    def __init__(self, data_size, cam_size):
        """ Arguments:
            * data_size: (bit count) The size of the data
            * cam_size: (entry count) The number of entries in the CAM
        """

        # Internal
        self.cam_size = cam_size
        self.encoder = AddressEncoder(cam_size)
        self.decoder = Decoder(cam_size)
        self.entry_array = Array(CamEntry(data_size) for x in range(cam_size))
        self.vector_assembler = VectorAssembler(cam_size)

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
        # AddressEncoder for match types and output address
        m.submodules.AddressEncoder = self.encoder
        # Decoder is used to select which entry will be written to
        m.submodules.Decoder = self.decoder
        # CamEntry Array Submodules
        # Note these area added anonymously
        entry_array = self.entry_array
        m.submodules += entry_array
        # VectorAssembler Submodule
        m.submodules.VectorAssembler = self.vector_assembler

        # Decoder logic
        m.d.comb += [
            self.decoder.i.eq(self.address_in),
            self.decoder.n.eq(0)
        ]

        with m.If(self.enable):
            # Set the key value for every CamEntry
            for index in range(self.cam_size):

                # Write Operation
                with m.If(self.write_enable):
                    with m.If(self.decoder.o[index]):
                        m.d.comb += entry_array[index].command.eq(2)
                    with m.Else():
                        m.d.comb += entry_array[index].command.eq(0)

                # Read Operation
                with m.Else():
                    m.d.comb += entry_array[index].command.eq(1)

                # Send data input to all entries
                m.d.comb += entry_array[index].data_in.eq(self.data_in)
                # Send all entry matches to encoder
                ematch = entry_array[index].match
                m.d.comb += self.vector_assembler.i[index].eq(ematch)

            # Give input to and accept output from encoder module
            m.d.comb += [
                self.encoder.i.eq(self.vector_assembler.o),
                self.single_match.eq(self.encoder.single_match),
                self.multiple_match.eq(self.encoder.multiple_match),
                self.match_address.eq(self.encoder.o)
            ]

        # If the CAM is not enabled set all outputs to 0
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

