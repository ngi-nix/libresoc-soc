class SimState:
    def __init__(self, sim):
        self.sim = sim

    def get_intregs(self):
        self.intregs = []
        for i in range(32):
            simregval = self.sim.gpr[i].asint()
            self.intregs.append(simregval)

# HDL class here with same functions
