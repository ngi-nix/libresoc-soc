from nmigen import Memory, Module, Signal
from nmigen.cli import main
from PermissionValidator import PermissionValidator

class TLB():
    def __init__(self):
        # Inputs
        self.xwr = Signal(3) # Execute, Write, Read
        self.super = Signal(1) # Supervisor Mode
        self.super_access = Signal(1) # Supervisor Access
        self.command = Signal(2) # 00=None, 01=Search, 10=Write PTE, 11=Reset
        self.mode = Signal(4) # 4 bits for access to Sv48 on Rv64
        self.asid = Signal(15) # Address Space IDentifier (ASID)
        self.vma = Signal(36) # Virtual Memory Address (VMA)
        self.pte_in = Signal(64) # To be saved Page Table Entry (PTE)
        
        # Outputs
        self.hit = Signal(1) # Denotes if the VMA had a mapped PTE
        self.valid = Signal(1) # Denotes if the permissions are correct
        self.pteOut = Signal(64) # PTE that was mapped to by the VMA
        
        # Cam simulations
        mem_l1 = Memory(113, 32) # L1 TLB cache
        read_port_l1 = mem_l1.read_port
        write_port_l1 = mem_l1.write_port
        
        mem_l2 = Memory(113, 128) # L2 TLB cache
        read_port_l2 = mem_l2.read_port
        write_port_l2 = mem_l2.write_port
        
        def elaborate(self, platform):
            m = Module()
            m.d.submodules.perm_valid = perm_valid = PermissionValidator(113)
            m.d.sync += [
                Case(self.command, {
                   # Search for PTE
                   1: [
                       # Check first entry in set
                       # TODO make module?
                       read_port_l1.addr.eq(vma[0,2]),
                       If(read_port_l1.data[0] == 1,
                          perm_valid.data.eq(read_port_l1.data),
                          perm_valid.xwr.eq(self.xwr),
                          perm_valid.super.eq(self.super),
                          perm_valid.super_access.eq(self.super_access),
                          perm_valid.asid.eq(self.asid),
                          self.valid,eq(perm_valid.valid)
                       ),
                       If(self.valid == 0,
                          read_port_l1.addr.eq(vma[0,2] + 1),
                          If(read_port_l1.data[0] == 1,
                             perm_valid.data.eq(read_port_l1.data),
                             perm_valid.xwr.eq(self.xwr),
                             perm_valid.super.eq(self.super),
                             perm_valid.super_access.eq(self.super_access),
                             perm_valid.asid.eq(self.asid),
                             self.valid,eq(perm_valid.valid)
                          )                          
                       )
                       ]
                })
            ]
        
thing = TLB()
print("Gottem")
