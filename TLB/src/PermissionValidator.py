from nmigen import Signal
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
        self.super = Signal(1) # Supervisor Mode
        self.super_access = Signal(1) # Supervisor Access
        self.asid = Signal(15) # Address Space IDentifier (ASID)

        # Output
        self.valid = Signal(1) # Denotes if the permissions are correct

    def elaborate(self, platform):
        m = Module()
        # ASID match or Global Permission
        with m.If(data[64:78] == self.asid | data[5]):
            # Check Execute, Write, Read (XWR) Permissions
            with m.If(data[3] == self.xwr[2] \
                      & data[2] == self.xwr[1] \
                      & data[1] == self.xwr[0]):
                # Supervisor Logic
                with m.If(self.super):
                    # Valid if entry is not in user mode or supervisor
                    # has Supervisor User Memory (SUM) access via the
                    # SUM bit in the sstatus register
                    m.comb += self.valid.eq(~data[4] | self.super_access)
                # User logic
                with m.Else():
                    # Valid if the entry is in user mode only
                    m.comb += self.valid.eq(data[4])
            with m.Else():
                m.comb += self.valid.eq(0)
        with m.Else():
            m.comb += self.valid.eq(0)