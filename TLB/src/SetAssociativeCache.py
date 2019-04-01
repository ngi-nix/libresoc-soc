from nmigen import Array, Memory, Module, Signal
from nmigen.cli import main

from AddressEncoder import AddressEncoder

class SetAssociativeCache():
    """ Set Associative Cache Memory

        The purpose of this module is to generate a memory cache given the
        constraints passed in. This will create a n-way set associative cache.
        It is expected for the SV TLB that the VMA will provide the set number
        while the ASID provides the tag (still to be decided).

    """
    def __init__(self, tag_size, data_size, set_count, way_count):
        """ Arguments
        """
        # Internal
        # Memory
        # Plus one for valid bit. Valid bit will be the LSB in the memory
        memory_array = Array(Memory(tag_size + data_size + 1, entry_count))
        self.read_port_array = Array()
        self.write_port_array = Array()
        for i in range(way_count):
            self.read_port_array.append(memory_array[i].read_port())
            self.write_port_array.append(memory_array[i].write_port())
        self.way_count = way_count
        self.tag_size = tag_size
        self.data_size = data_size
        # Encoder
        self.encoder = AddressEncoder(max=way_count)

        # Input
        self.enable = Signal(1)
        self.command = Signal(2) # 00=None, 01=Read, 10=Write
        self.set = Signal(max=set_count)
        self.tag = Signal(tag_size)
        self.data_i = Signal(data_size + tag_size)

        # Output
        self.hit = Signal(1)
        self.multiple_hit = Signal(1) # Oh no
        self.data_o = Signal(data_size)

    def elaborate(self, platform=None):
        m = Module()
        m.submodules += self.read_port_array
        m.submodules += self.write_port_array

        with m.If(self.enable):
            with m.Switch(self.command):
                # Search all sets at a particular tag
                with m.Case("01"):
                    # Vector to store valid results
                    valid_vector = []
                    # Loop through memory setting what set to read
                    for i in range(self.way_count):
                        n.d.comb += [
                            self.write_port_array[i].en.eq(0),
                            self.read_port_array[i].addr.eq(self.set)
                        ]
                        # Pull out Valid bit from data
                        data = self.read_port_array[i].data;
                        valid_bit = data[0];
                        # Validate given tag vs stored tag
                        tag_start = 1 + self.data_size
                        tag_end = 1 + self.data_size + self.tag_size;
                        tag = data[tag_start:tag_end]
                        tag_valid = self.tag == tag
                        # An entry is only valid if the tags match AND
                        # is marked as a valid entry
                        valid_vector.append(tag_valid & valid_bit)

                    # Pass encoder the valid vector
                    self.encoder.i.eq(Cat(*valid_vector))
                    # Only one entry should be marked
                    # This is due to already verifying the tags
                    # matched and the valid bit is high
                    with m.If(self.encoder.single_match):
                        # Pull out data from the read port
                        read_port = self.read_port_array[self.encoder.o]
                        data_start = 1
                        data_end = 1 + self.data_size
                        data = read_port.data[data_start:data_end]
                        m.d.comb += [
                            self.hit.eq(1),
                            self.multiple_hit.eq(0),
                            self.data_o.eq(data)
                        ]
                    # Oh no! Seal the gates! Multiple tags matched?!? kasd;ljkafdsj;k
                    with m.Elif(self.encoder.multiple_match):
                        m.d.comb += [
                            self.hit.eq(0),
                            self.multiple_hit.eq(1),
                            self.data_o.eq(0)
                        ]
                    # No tag matches means no data
                    with m.Else():
                        m.d.comb += [
                            self.hit.eq(0),
                            self.multiple_hit.eq(0),
                            self.data_o.eq(0)
                        ]
                # TODO
                # Write to a given tag
                # with m.Case("10"):
                    # Search for available space
                    # What to do when there is no space
                    # Maybe catch multiple tags write here?
                    # TODO
        return m