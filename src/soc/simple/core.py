"""simple core

not in any way intended for production use.  connects up FunctionUnits to
Register Files in a brain-dead fashion that only permits one and only one
Function Unit to be operational.
"""
from nmigen import Elaboratable, Module, Signal
from nmigen.cli import rtlil

from nmutil.picker import PriorityPicker
from nmutil.util import treereduce

from soc.fu.compunits.compunits import AllFunctionUnits
from soc.regfile.regfiles import RegFiles
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2



def ortreereduce(tree, attr="data_o"):
    return treereduce(tree, operator.or_, lambda x: getattr(x, attr))


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

        # enable-signals for each FU, get one bit for each FU (by name)
        fu_enable = Signal(len(fus), reset_less=True)
        fu_bitdict = {}
        for i, funame in enumerate(fus.keys()):
            fu_bitdict[funame] = fu_enable[i]

        # dictionary of lists of regfile read ports
        byregfiles_rd = {}
        byregfiles_rdspec = {}
        for (funame, fu) in fus.items():
            print ("read ports for %s" % funame)
            for idx in range(fu.n_src):
                (regfile, regname, wid) = fu.get_in_spec(idx)
                print ("    %s %s %s" % (regfile, regname, str(wid)))
                rdflag, read, _ = dec2.regspecmap(regfile, regname)
                if regfile not in byregfiles_rd:
                    byregfiles_rd[regfile] = {}
                    byregfiles_rdspec[regfile] = (regname, rdflag, read, wid)
                # here we start to create "lanes"
                if idx not in byregfiles_rd[regfile]:
                    byregfiles_rd[regfile][idx] = []
                fuspec = (funame, fu)
                byregfiles_rd[regfile][idx].append(fuspec)

        # ok just print that out, for convenience
        for regfile, spec in byregfiles_rd.items():
            print ("regfile read ports:", regfile)
            for idx, fuspec in spec.items():
                print ("  regfile read port %s lane: %d" % (regfile, idx))
                (regname, rdflag, read, wid) = byregfiles_rdspec[regfile]
                print ("  %s" % regname, wid, read, rdflag)
                for (funame, fu) in fuspec:
                    print ("    ", funame, fu, fu.src_i[idx])
                    print ()

        # okaay, now we need a PriorityPicker per regfile per regfile port
        # loootta pickers... peter piper picked a pack of pickled peppers...
        rdpickers = {}
        for regfile, spec in byregfiles_rd.items():
            rdpickers[regfile] = {}
            for rpidx, (idx, fuspec) in enumerate(spec.items()):
                # get the regfile specs for this regfile port
                (regname, rdflag, read, wid) = byregfiles_rdspec[regfile]

                # "munge" the regfile port index, due to full-port access
                if regfile in ['XER', 'CR']:
                    if regname.startswith('full'):
                        rpidx = 0 # by convention, first port
                    else:
                        rpidx += 1 # start indexing port 0 from 1

                # select the required read port.  these are pre-defined sizes
                print (regfile, regs.rf.keys())
                rport = regs.rf[regfile.lower()].r_ports[rpidx]

                # create a priority picker to manage this port
                rdpickers[regfile][idx] = rdpick = PriorityPicker(len(fuspec))
                setattr(m.submodules, "rdpick_%s_%d" % (regfile, idx), rdpick)

                # connect the regspec "reg select" number to this port
                with m.If(rdpick.en_o):
                    comb += rport.ren.eq(read)

                # connect up the FU req/go signals and the reg-read to the FU
                for pi, (funame, fu) in enumerate(fuspec):
                    # connect request-read to picker input, and output to go-rd
                    fu_active = fu_bitdict[funame]
                    comb += rdpick.i[pi].eq(fu.rd_rel_o[idx] & fu_active)
                    comb += fu.go_rd_i[idx].eq(rdpick.o[pi])
                    # connect regfile port to input
                    comb += fu.src_i[idx].eq(rport.data_o)

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
