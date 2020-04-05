from caller import ISACaller
from fixedarith import fixedarith
from fixedload import fixedload
from fixedstore import fixedstore
from soc.decoder.isa.caller import ISACaller


class ISA(ISACaller):
    def __init__(self, dec, regs):
        super().__init__(dec, regs)
        self.fixedarith = fixedarith()
        self.fixedload = fixedload()
        self.fixedstore = fixedstore()

        self.instrs = {
            **self.fixedarith.fixedarith_instrs,
            **self.fixedload.fixedload_instrs,
            **self.fixedstore.fixedstore_instrs,
        }
