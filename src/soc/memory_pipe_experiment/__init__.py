from nmigen import Elaboratable, Module, Signal


class L1Cache(Elaboratable):
    def __init__(self, config):
        self.config = config
