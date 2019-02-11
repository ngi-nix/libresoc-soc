from nmigen import Signal, Module
from nmigen.cli import main

# The purpose of this Module is to check the Permissions of a given PTE 
# against the requested access permissions. 
# This module will either validate (by setting the valid bit HIGH) the request
# or find a permission fault and invalidate (by setting the valid bit LOW) 
# the request
class PermissionValidator():
    def __init__(self, data_size):
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
        m.d.comb += [
            # Check if ASID matches OR entry is global
            If(data[98:113] == self.asid or data[5] == 1,
               # Check Execute, Write, Read (XWR) Permissions
               If(data[3] == self.xwr[2] and data[2] == self.xwr[1] and data[1] == self.xwr[0],
                  # Check if supervisor
                  If(self.super == 1,
                     # Check if entry is in user mode
                     # Check if supervisor has access
                     If(data[4] == 0,
                        self.valid.eq(1)
                     ).Elif(self.super_access == 1,
                        self.valid.eq(1)
                     ).Else(
                        self.valid.eq(0)
                     )
                  ).Else(
                      # Check if entry is in user mode
                      If(data[4] == 1,
                         self.valid.eq(1)
                      ).Else(
                         self.valid.eq(0) 
                      )
                  )
               ).Else(
                   self.valid.eq(0)                   
               )
            ).Else(
                self.valid.eq(0)
            )
        ]
