""" TLB Module

    The expected form of the data is:
    * Item (Bits)
    * Tag (N - 79) / ASID (78 - 64) / PTE (63 - 0)
"""

from nmigen import Memory, Module, Signal, Cat, Elaboratable
from nmigen.cli import main

from .PermissionValidator import PermissionValidator
from .Cam import Cam


class TLB(Elaboratable):
    def __init__(self, asid_size, vma_size, pte_size, L1_size):
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
        self.cam_L1 = Cam(vma_size, L1_size)
        self.mem_L1 = Memory(width=asid_size + pte_size, depth=L1_size)

        # Permission Validator
        self.perm_validator = PermissionValidator(asid_size, pte_size)

        # Inputs
        self.supermode = Signal(1)  # Supervisor Mode
        self.super_access = Signal(1)  # Supervisor Access
        # 00=None, 01=Search, 10=Write L1, 11=Write L2
        self.command = Signal(2)
        self.xwr = Signal(3)  # Execute, Write, Read
        self.mode = Signal(4)  # 4 bits for access to Sv48 on Rv64
        self.address_L1 = Signal(range(L1_size))
        self.asid = Signal(asid_size)  # Address Space IDentifier (ASID)
        self.vma = Signal(vma_size)  # Virtual Memory Address (VMA)
        self.pte_in = Signal(pte_size)  # To be saved Page Table Entry (PTE)

        # Outputs
        self.hit = Signal(1)  # Denotes if the VMA had a mapped PTE
        self.perm_valid = Signal(1)  # Denotes if the permissions are correct
        self.pte_out = Signal(pte_size)  # PTE that was mapped to by the VMA

    def search(self, m, read_L1, write_L1):
        """ searches the TLB
        """
        m.d.comb += [
            write_L1.en.eq(0),
            self.cam_L1.write_enable.eq(0),
            self.cam_L1.data_in.eq(self.vma)
        ]
        # Match found in L1 CAM
        match_found = Signal(reset_less=True)
        m.d.comb += match_found.eq(self.cam_L1.single_match
                                   | self.cam_L1.multiple_match)
        with m.If(match_found):
            # Memory shortcut variables
            mem_address = self.cam_L1.match_address
            # Memory Logic
            m.d.comb += read_L1.addr.eq(mem_address)
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
                self.perm_validator.super_mode.eq(self.supermode),
                # Supverisor Access
                self.perm_validator.super_access.eq(self.super_access),
                # Address Space IDentifier (ASID)
                self.perm_validator.asid.eq(self.asid),
                # Output result of permission validation
                self.perm_valid.eq(self.perm_validator.valid)
            ]
            # Only output PTE if permissions are valid
            with m.If(self.perm_validator.valid):
                # XXX TODO - dummy for now
                reg_data = Signal.like(self.pte_out)
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

    def write_l1(self, m, read_L1, write_L1):
        """ writes to the L1 cache
        """
        # Memory_L1 Logic
        m.d.comb += [
            write_L1.en.eq(1),
            write_L1.addr.eq(self.address_L1),
            # The Cat places arguments from LSB -> MSB
            write_L1.data.eq(Cat(self.pte_in, self.asid))
        ]
        # CAM_L1 Logic
        m.d.comb += [
            self.cam_L1.write_enable.eq(1),
            self.cam_L1.data_in.eq(self.vma),  # data_in is sent to all entries
            # self.cam_L1.address_in.eq(todo) # a CAM entry needs to be selected

        ]

    def elaborate(self, platform):
        m = Module()
        # Add submodules
        # Submodules for L1 Cache
        m.submodules.cam_L1 = self.cam_L1
        m.submodules.read_L1 = read_L1 = self.mem_L1.read_port()
        m.submodules.write_L1 = write_L1 = self.mem_L1.write_port()

        # Permission Validator Submodule
        m.submodules.perm_valididator = self.perm_validator

        # When MODE specifies translation
        # TODO add in different bit length handling ie prefix 0s
        tlb_enable = Signal(reset_less=True)
        m.d.comb += tlb_enable.eq(self.mode != 0)

        with m.If(tlb_enable):
            m.d.comb += [
                self.cam_L1.enable.eq(1)
            ]
            with m.Switch(self.command):
                # Search
                with m.Case("01"):
                    self.search(m, read_L1, write_L1)

                # Write L1
                # Expected that the miss will be handled in software
                with m.Case("10"):
                    self.write_l1(m, read_L1, write_L1)

                # TODO
                # with m.Case("11"):

        # When disabled
        with m.Else():
            m.d.comb += [
                self.cam_L1.enable.eq(0),
                # XXX TODO - self.reg_file.enable.eq(0),
                self.hit.eq(0),
                self.perm_valid.eq(0),  # XXX TODO, check this
                self.pte_out.eq(0)
            ]
        return m


if __name__ == '__main__':
    tlb = TLB(15, 36, 64, 4)
    main(tlb, ports=[tlb.supermode, tlb.super_access, tlb.command,
                     tlb.xwr, tlb.mode, tlb.address_L1, tlb.asid,
                     tlb.vma, tlb.pte_in,
                     tlb.hit, tlb.perm_valid, tlb.pte_out,
                     ] + tlb.cam_L1.ports())
