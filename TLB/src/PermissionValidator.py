from nmigen import Module, Signal
from nmigen.cli import main

class PermissionValidator():
    """ The purpose of this Module is to check the Permissions of a given PTE
        against the requested access permissions.

        This module will either validate (by setting the valid bit HIGH)
        the request or find a permission fault and invalidate (by setting
        the valid bit LOW) the request
    """

    def __init__(self, data_size):
        """ Arguments:
            * data_size: (bit count) The size of the data words being processed

            Return:
            * valid HIGH when permissions are correct
        """
        # Input
        self.data = Signal(data_size);
        self.xwr = Signal(3) # Execute, Write, Read
        self.super_mode = Signal(1) # Supervisor Mode
        self.super_access = Signal(1) # Supervisor Access
        self.asid = Signal(15) # Address Space IDentifier (ASID)

        # Output
        self.valid = Signal(1) # Denotes if the permissions are correct

    def elaborate(self, platform=None):
        m = Module()
        # Check if the entry is valid
        with m.If(self.data[0]):
            # ASID match or Global Permission
            # Note that the MSB bound is exclusive
            with m.If((self.data[64:79] == self.asid) | self.data[5]):
                # Check Execute, Write, Read (XWR) Permissions
                with m.If((self.data[3] == self.xwr[2]) \
                          & (self.data[2] == self.xwr[1]) \
                          & (self.data[1] == self.xwr[0])):
                    # Supervisor Logic
                    with m.If(self.super_mode):
                        # Valid if entry is not in user mode or supervisor
                        # has Supervisor User Memory (SUM) access via the
                        # SUM bit in the sstatus register
                        m.d.comb += self.valid.eq((~self.data[4]) | self.super_access)
                    # User logic
                    with m.Else():
                        # Valid if the entry is in user mode only
                        m.d.comb += self.valid.eq(self.data[4])
                with m.Else():
                    m.d.comb += self.valid.eq(0)
            with m.Else():
                m.d.comb += self.valid.eq(0)
        with m.Else():
            m.d.comb += self.valid.eq(0)
        return m