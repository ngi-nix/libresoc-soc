# Reads OpenPOWER ISA pages from http://libre-riscv.org/openpower/isa
from collections import namedtuple, OrderedDict
from copy import copy
import os

op = namedtuple("Ops", ("desc", "form", "opcode", "regs", "pcode", "sregs"))

def get_isa_dir():
    fdir = os.path.abspath(os.path.dirname(__file__))
    fdir = os.path.split(fdir)[0]
    fdir = os.path.split(fdir)[0]
    fdir = os.path.split(fdir)[0]
    fdir = os.path.split(fdir)[0]
    return os.path.join(fdir, "libreriscv", "openpower", "isa")

class ISA:

    def __init__(self):
        self.instr = OrderedDict()

    def read_file(self, fname):
        fname = os.path.join(get_isa_dir(), fname)
        with open(fname) as f:
            lines = f.readlines()
        
        d = {}
        l = lines.pop(0).rstrip() # get first line
        while lines:
            print (l)
            # expect get heading
            assert l.startswith('#'), ("# not found in line %s" % l)
            d['desc'] = l[1:].strip()

            # whitespace expected
            l = lines.pop(0).strip()
            print (repr(l))
            assert len(l) == 0, ("blank line not found %s" % l)

            # Form expected
            l = lines.pop(0).strip()
            assert l.endswith('-Form'), ("line with -Form expected %s" % l)
            d['form'] = l.split('-')[0]

            # whitespace expected
            l = lines.pop(0).strip()
            assert len(l) == 0, ("blank line not found %s" % l)

            # get list of opcodes
            li = []
            while True:
                l = lines.pop(0).strip()
                if len(l) == 0: break
                assert l.startswith('*'), ("* not found in line %s" % l)
                l = l[1:].split(' ') # lose star
                l = filter(lambda x: len(x) != 0, l) # strip blanks
                li.append(list(l))
            opcodes = li

            # get pseudocode
            li = []
            while True:
                l = lines.pop(0).rstrip()
                if len(l) == 0: break
                assert l.startswith('    '), ("4spcs not found in line %s" % l)
                l = l[4:] # lose 4 spaces
                li.append(l)
            d['pcode'] = li

            # "Special Registers Altered" expected
            l = lines.pop(0).rstrip()
            assert l.startswith("Special"), ("special not found %s" % l)

            # whitespace expected
            l = lines.pop(0).strip()
            assert len(l) == 0, ("blank line not found %s" % l)

            # get special regs
            li = []
            while lines:
                l = lines.pop(0).rstrip()
                if len(l) == 0: break
                assert l.startswith('    '), ("4spcs not found in line %s" % l)
                l = l[4:] # lose 4 spaces
                li.append(l)
            d['sregs'] = li

            # add in opcode
            for o in opcodes:
                opcode, regs = o[0], o[1:]
                op = copy(d)
                op['regs'] = regs
                op['opcode'] = opcode
                self.instr[opcode] = op

            # expect and drop whitespace
            while lines:
                l = lines.pop(0).rstrip()
                if len(l) != 0: break

    def pprint_ops(self):
        for k, v in self.instr.items():
            print ("# %s %s" % (v['opcode'], v['desc']))
            print ("Form: %s Regs: %s" % (v['form'], v['regs']))
            print ('\n'.join(map(lambda x: "    %s" % x, v['pcode'])))
            print ("Specials")
            print ('\n'.join(map(lambda x: "    %s" % x, v['sregs'])))
            print ()

if __name__ == '__main__':
    isa = ISA()
    for pth in os.listdir(os.path.join(get_isa_dir())):
        print (get_isa_dir(), pth)
        assert pth.endswith(".mdwn"), "only %s in isa dir" % pth
        isa.read_file(pth)

    isa.pprint_ops()
