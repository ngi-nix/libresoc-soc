class TestCase:
    def __init__(self, program, name, regs=None, sprs=None, cr=0, mem=None):

        self.program = program
        self.name = name

        if regs is None:
            regs = [0] * 32
        if sprs is None:
            sprs = {}
        if mem is None:
            mem = {}
        self.regs = regs
        self.sprs = sprs
        self.cr = cr
        self.mem = mem
