""" TLB Module

    The expected form of the data is:
    * Item (Bits)
    * Tag (N - 79) / ASID (78 - 64) / PTE (63 - 0)
"""

from nmigen import Memory, Module, Signal
from nmigen.cli import main

from PermissionValidator import PermissionValidator
from Cam import Cam

class TLB():
    def __init__(self, asid_size, vma_size, pte_size):
        """ Arguments
            * asid_size: Address Space IDentifier (ASID) typically 15 bits
            * vma_size: Virtual Memory Address (VMA) typically 36 bits
            * pte_size: Page Table Entry (PTE) typically 64 bits

            Notes:
            These arguments should represent the largest possible size
            defined by the MODE settings. See
            Volume II: RISC-V Privileged Architectures V1.10 Page 57
        """

        # Internal
        self.state = 0
        # L1 Cache Modules
        L1_size = 8
        self.cam_L1 = Cam(vma_size, cam_size)
        self.mem_L1 = Memory(asid_size + pte_size, cam_size)

        # Permission Validator
        self.perm_validator = PermissionValidator(asid_size + pte_size)

        # Inputs
        self.supermode = Signal(1) # Supervisor Mode
        self.super_access = Signal(1) # Supervisor Access
        self.command = Signal(2) # 00=None, 01=Search, 10=Write L1, 11=Write L2
        self.xwr = Signal(3) # Execute, Write, Read
        self.mode = Signal(4) # 4 bits for access to Sv48 on Rv64
        self.address_L1 = Signal(max= am_size)
        self.asid = Signal(asid_size) # Address Space IDentifier (ASID)
        self.vma = Signal(vma_size) # Virtual Memory Address (VMA)
        self.pte_in = Signal(pte_size) # To be saved Page Table Entry (PTE)

        # Outputs
        self.hit = Signal(1) # Denotes if the VMA had a mapped PTE
        self.perm_valid = Signal(1) # Denotes if the permissions are correct
        self.pte_out = Signal(pte_size) # PTE that was mapped to by the VMA

        def elaborate(self, platform):
            m = Module()
            # Add submodules
            # Submodules for L1 Cache
            m.d.submodules.cam_L1 = self.cam_L1
            m.d.sumbmodules.read_L1 = read_L1 = self.mem_L1.read_port
            m.d.sumbmodules.read_L1 = write_L1 = self.mem_L1.read_port
            # Permission Validator Submodule
            m.d.submodules.perm_valididator = self.perm_validator

            # When MODE specifies translation
            # TODO add in different bit length handling ie prefix 0s
            with m.If(self.mode != 0):
                m.d.comb += [
                    self.cam_L1.enable.eq(1)
                ]
                with m.Switch(self.command):
                    # Search
                    with m.Case("01"):
                        m.d.comb += [
                            write_L1.en.eq(0),
                            self.cam_L1.write_enable.eq(0),
                            self.cam_L1.data_in.eq(self.vma)
                        ]
                    # Write L1
                    # Expected that the miss will be handled in software
                    with m.Case("10"):
                        # Memory_L1 Logic
                        m.d.comb += [
                            write_L1.en.eq(1),
                            write_L1.addr.eq(self.address_L1),
                            # The first argument is the LSB
                            write_L1.data.eq(Cat(self.pte, self.asid))
                        ]
                        # CAM_L1 Logic
                        m.d.comb += [
                            self.cam_L1.write_enable.eq(1),
                            self.cam_L1.data_in.eq(self.vma),
                        ]
                    # TODO
                    #with m.Case("11"):

                # Match found in L1 CAM
                with m.If(self.cam_L1.single_match
                          | self.cam_L1.multiple_match):
                    # Memory shortcut variables
                    mem_addrress = self.cam_L1.match_address
                    # Memory Logic
                    m.d.comb += read_L1.addr(mem_address)
                    # Permission Validator Logic
                    m.d.comb += [
                        self.hit.eq(1),
                        # Set permission validator data to the correct
                        # register file data according to CAM match
                        # address
                        self.perm_validator.data.eq(read_L1.data),
                        # Execute, Read, Write
                        self.perm_validator.xwr.eq(self.xwr),
                        # Supervisor Mode
                        self.perm_validator.supermode.eq(self.supermode),
                        # Supverisor Access
                        self.perm_validator.super_access.eq(self.super_access),
                        # Address Space IDentifier (ASID)
                        self.perm_validator.asid.eq(self.asid),
                        # Output result of permission validation
                        self.perm_valid.eq(self.perm_validator.valid)
                    ]
                    # Do not output PTE if permissions fail
                    with m.If(self.perm_validator.valid):
                        m.d.comb += [
                            self.pte_out.eq(reg_data)
                            ]
                    with m.Else():
                        m.d.comb += [
                            self.pte_out.eq(0)
                        ]
                # Miss Logic
                with m.Else():
                    m.d.comb += [
                        self.hit.eq(0),
                        self.perm_valid.eq(0),
                        self.pte_out.eq(0)
                    ]
            # When disabled
            with m.Else():
                m.d.comb += [
                    self.cam_L1.enable.eq(0),
                    self.reg_file.enable.eq(0),
                    self.hit.eq(0),
                    self.valid.eq(0),
                    self.pte_out.eq(0)
                ]
            return m

