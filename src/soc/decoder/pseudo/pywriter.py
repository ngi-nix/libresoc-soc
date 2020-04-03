# python code-writer for OpenPOWER ISA pseudo-code parsing

import os
from soc.decoder.pseudo.pagereader import ISA
from soc.decoder.power_pseudo import convert_to_python

def get_isasrc_dir():
    fdir = os.path.abspath(os.path.dirname(__file__))
    fdir = os.path.split(fdir)[0]
    return os.path.join(fdir, "isa")

def create_args(reglist, extra=None):
    args = set()
    for reg in reglist:
        args.add(reg)
    args = list(args)
    if extra:
        args = [extra] + args
    return ', '.join(args)


class PyISAWriter(ISA):
    def __init__(self):
        ISA.__init__(self)

    def write_pysource(self, pagename):
        instrs = isa.page[pagename]
        isadir = get_isasrc_dir()
        fname = os.path.join(isadir, "%s.py" % pagename)
        with open(fname, "w") as f:
            iinf = ''
            f.write("from soc.decoder.isa import ISACaller\n\n")
            f.write("class %s(ISACaller):\n" % pagename)
            for page in instrs:
                d = self.instr[page]
                print (fname, d.opcode)
                pcode = '\n'.join(d.pcode) + '\n'
                print (pcode)
                pycode, rused = convert_to_python(pcode)
                # create list of arguments to call
                regs = rused['read_regs'] + rused['uninit_regs']
                args = create_args(regs, 'self')
                # create list of arguments to return
                retargs = create_args(rused['write_regs'])
                f.write("    def %s(%s):\n" % (page.replace(".", "_"), args))
                pycode = pycode.split("\n")
                pycode = '\n'.join(map(lambda x: "        %s" % x, pycode))
                pycode = pycode.rstrip()
                f.write(pycode + '\n')
                if retargs:
                    f.write("        return (%s,)\n\n" % retargs)
                else:
                    f.write("\n")
                # cumulate the instruction info
                iinfo = "('%s', %s, %s, %s)" % \
                            (pagename, rused['read_regs'],
                            rused['uninit_regs'], rused['write_regs'])
                iinf += "    instrs['%s'] = %s\n" % (pagename, iinfo)
            f.write("    instrs = {}\n")
            f.write(iinf)

if __name__ == '__main__':
    isa = PyISAWriter()
    isa.write_pysource('comparefixed')
    isa.write_pysource('fixedarith')
