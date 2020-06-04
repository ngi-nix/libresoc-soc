class TestCase:
    def __init__(self, program, name, regs=None, sprs=None, cr=0):
        self.program = program
        self.name = name

        if regs is None:
            regs = [0] * 32
        if sprs is None:
            sprs = {}
        self.regs = regs
        self.sprs = sprs
        self.cr = cr

