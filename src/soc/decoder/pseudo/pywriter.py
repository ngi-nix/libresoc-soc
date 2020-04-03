# python code-writer for OpenPOWER ISA pseudo-code parsing

import os
from soc.decoder.pseudo.pagereader import ISA
from soc.decoder.power_pseudo import convert_to_python

def get_isasrc_dir():
    fdir = os.path.abspath(os.path.dirname(__file__))
    fdir = os.path.split(fdir)[0]
    return os.path.join(fdir, "isa")


class PyISAWriter(ISA):
    def __init__(self):
        ISA.__init__(self)

    def write_pysource(self, pagename):
        instrs = isa.page[pagename]
        isadir = get_isasrc_dir()
        fname = os.path.join(isadir, "%s.py" % pagename)
        with open(fname, "w") as f:
            f.write("class %s:\n" % pagename)
            for page in instrs:
                d = self.instr[page]
                print (fname, d.opcode)
                pcode = '\n'.join(d.pcode) + '\n'
                print (pcode)
                pycode, regsused = convert_to_python(pcode)
                f.write("    #%s\n" % repr(regsused))
                f.write("    def %s(self):\n" % page.replace(".", "_"))
                pycode = pycode.split("\n")
                pycode = '\n'.join(map(lambda x: "        %s" % x, pycode))
                f.write("%s\n\n" % pycode)


if __name__ == '__main__':
    isa = PyISAWriter()
    isa.write_pysource('comparefixed')
    isa.write_pysource('fixedarith')
