"""simple core

not in any way intended for production use.  connects up FunctionUnits to
Register Files in a brain-dead fashion that only permits one and only one
Function Unit to be operational.
"""
from nmigen import Elaboratable, Module, Signal
from nmigen.cli import rtlil

from soc.fu.compunits.compunits import AllFunctionUnits
from soc.regfile.regfiles import RegFiles
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2


class NonProductionCore(Elaboratable):
    def __init__(self):
        self.fus = AllFunctionUnits()
        self.regs = RegFiles()
        self.pdecode = pdecode = create_pdecode()
        self.pdecode2 = PowerDecode2(pdecode)   # instruction decoder
        self.ivalid_i = self.pdecode2.e.valid   # instruction is valid

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        m.submodules.pdecode2 = dec2 = self.pdecode2
        m.submodules.fus = self.fus
        self.regs.elaborate_into(m, platform)
        regs = self.regs
        fus = self.fus.fus

        # dictionary of lists of regfile read ports
        byregfiles_rd = {}
        for (funame, fu) in fus.items():
            print ("read ports for %s" % funame)
            for idx in range(fu.n_src):
                (regfile, regname, wid) = fu.get_in_spec(idx)
                print ("    %s %s %s" % (regfile, regname, str(wid)))
                rdflag, read, _ = dec2.regspecmap(regfile, regname)
                if regfile not in byregfiles_rd:
                    byregfiles_rd[regfile] = {}
                # here we start to create "lanes"
                if idx not in byregfiles_rd[regfile]:
                    byregfiles_rd[regfile][idx] = []
                fuspec = (funame, fu, regname, rdflag, read, wid)
                byregfiles_rd[regfile][idx].append(fuspec)

        # ok just print that out, for convenience
        for regfile, spec in byregfiles_rd.items():
            print ("regfile read ports:", regfile)
            for idx, fuspec in spec.items():
                print ("  regfile read port %s lane: %d" % (regfile, idx))
                for (funame, fu, regname, rdflag, read, wid) in fuspec:
                    print ("    ", funame, regname, wid, read, rdflag)
                    print ("    ", fu)
                    print ()

        return m

    def __iter__(self):
        yield from self.fus.ports()
        yield from self.pdecode2.ports()
        # TODO: regs

    def ports(self):
        return list(self)


if __name__ == '__main__':
    dut = NonProductionCore()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("non_production_core.il", "w") as f:
        f.write(vl)
