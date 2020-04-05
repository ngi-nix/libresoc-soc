from caller import ISACaller
from fixedarith import fixedarith
from fixedload import fixedload
from fixedstore import fixedstore
from soc.decoder.isa.caller import ISACaller


class ISA(ISACaller):
    def __init__(self, dec, regs):
        super().__init__(dec, regs)
        self.fixedarith = fixedarith(dec, regs)
        self.fixedload = fixedload(dec, regs)
        self.fixedstore = fixedstore(dec, regs)

        self.instrs = {
            **self.fixedarith.instrs,
            **self.fixedload.instrs,
            **self.fixedstore.instrs,
        }
