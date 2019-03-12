from nmigen import Array, Module, Signal
from nmigen.lib.coding import Decoder

class RegisterFile():
    """ Register File

        The purpose of this module is to represent a bank of registers.

        Usage:
        To Write: Set the address line to the desired register in the file, set
        write_enable HIGH, and wait one cycle
        To Read: Set the address line to the desired register in the file, set
        write_enable LOW, and wait one cycle.
    """

    def __init__(self, data_size, file_size):
        """ Arguments:
            * data_size: (bit count) The number of bits in one register
            * cam_size: (entry count) the number of registers in this file
        """

        # Internal
        self.register_array = Array(Signal(data_size) for x in range(file_size))

        # Input
        self.enable = Signal(1)
        self.write_enable = Signal(1)
        self.address = Signal(max=file_size)
        self.data_i = Signal(data_size)

        # Output
        self.valid = Signal(1)
        self.data_o = Signal(data_size)

    def elaborate(self, platform=None):
        m = Module()

        with m.If(self.enable):
            # Write Logic
            with m.If(self.write_enable):
                m.d.sync += [
                    self.valid.eq(0),
                    self.data_o.eq(0),
                    self.register_array[self.address].eq(self.data_i)
                ]
            # Read Logic
            with m.Else():
                m.d.sync += [
                    self.valid.eq(1),
                    self.data_o.eq(self.register_array[self.address])
                ]
        # Invalidate results when not enabled
        with m.Else():
            m.d.sync += [
                self.valid.eq(0),
                self.data_o.eq(0)
            ]

        return m
