from nmigen import Module, Signal, Elaboratable
from nmigen.cli import main

from soc.TLB.PteEntry import PteEntry


class PermissionValidator(Elaboratable):
    """ The purpose of this Module is to check the Permissions of a given PTE
        against the requested access permissions.

        This module will either validate (by setting the valid bit HIGH)
        the request or find a permission fault and invalidate (by setting
        the valid bit LOW) the request
    """

    def __init__(self, asid_size, pte_size):
        """ Arguments:
            * asid_size: (bit count) The size of the asid to be processed
            * pte_size: (bit count) The size of the pte to be processed

            Return:
            * valid HIGH when permissions are correct
        """
        # Internal
        self.pte_entry = PteEntry(asid_size, pte_size)

        # Input
        self.data = Signal(asid_size + pte_size)
        self.xwr = Signal(3)  # Execute, Write, Read
        self.super_mode = Signal(1)  # Supervisor Mode
        self.super_access = Signal(1)  # Supervisor Access
        self.asid = Signal(15)  # Address Space IDentifier (ASID)

        # Output
        self.valid = Signal(1)  # Denotes if the permissions are correct

    def elaborate(self, platform=None):
        m = Module()

        m.submodules.pte_entry = self.pte_entry

        m.d.comb += self.pte_entry.i.eq(self.data)

        # Check if the entry is valid
        with m.If(self.pte_entry.v):
            # ASID match or Global Permission
            # Note that the MSB bound is exclusive
            with m.If((self.pte_entry.asid == self.asid) | self.pte_entry.g):
                # Check Execute, Write, Read (XWR) Permissions
                with m.If(self.pte_entry.xwr == self.xwr):
                    # Supervisor Logic
                    with m.If(self.super_mode):
                        # Valid if entry is not in user mode or supervisor
                        # has Supervisor User Memory (SUM) access via the
                        # SUM bit in the sstatus register
                        m.d.comb += self.valid.eq((~self.pte_entry.u)
                                                  | self.super_access)
                    # User logic
                    with m.Else():
                        # Valid if the entry is in user mode only
                        m.d.comb += self.valid.eq(self.pte_entry.u)
                with m.Else():
                    m.d.comb += self.valid.eq(0)
            with m.Else():
                m.d.comb += self.valid.eq(0)
        with m.Else():
            m.d.comb += self.valid.eq(0)
        return m
