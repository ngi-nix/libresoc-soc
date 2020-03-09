class CoreConfig:
    def __init__(self):
        self.N_SLICES = 16
        self.N_REGS = 4*self.N_SLICES
        self.ADDR_WIDTH_PHYS = 40
        self.ADDR_WIDTH_VIRT = 32
