# Reads OpenPOWER ISA pages from http://libre-riscv.org/openpower/isa
"""OpenPOWER ISA page parser

returns an OrderedDict of namedtuple "Ops" containing details of all
instructions listed in markdown files.

format must be strictly as follows (no optional sections) including whitespace:

# Compare Logical

X-Form

* cmpl BF,L,RA,RB

    if L = 0 then a <- [0]*32 || (RA)[32:63]
                  b <- [0]*32 || (RB)[32:63]
             else a <-  (RA)
                  b <-  (RB)
    if      a <u b then c <- 0b100
    else if a >u b then c <- 0b010
    else                c <-  0b001
    CR[4*BF+32:4*BF+35] <- c || XER[SO]

Special Registers Altered:

    CR field BF
    Another field

this translates to:

    # heading
    blank
    Some-Form
    blank
    * instruction registerlist
    * instruction registerlist
    blank
    4-space-indented pseudo-code
    4-space-indented pseudo-code
    blank
    Special Registers Altered:
    4-space-indented register description
    blank
    blank(s) (optional for convenience at end-of-page)
"""

from collections import namedtuple, OrderedDict
from copy import copy
import os

opfields = ("desc", "form", "opcode", "regs", "pcode", "sregs", "page")
Ops = namedtuple("Ops", opfields)


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
        self.forms = {}
        self.page = {}
        for pth in os.listdir(os.path.join(get_isa_dir())):
            print(get_isa_dir(), pth)
            if "swp" in pth:
                continue
            assert pth.endswith(".mdwn"), "only %s in isa dir" % pth
            self.read_file(pth)
            continue
            # code which helped add in the keyword "Pseudo-code:" automatically
            rewrite = self.read_file_for_rewrite(pth)
            name = os.path.join("/tmp", pth)
            with open(name, "w") as f:
                f.write('\n'.join(rewrite) + '\n')

    def read_file_for_rewrite(self, fname):
        pagename = fname.split('.')[0]
        fname = os.path.join(get_isa_dir(), fname)
        with open(fname) as f:
            lines = f.readlines()
        rewrite = []

        l = lines.pop(0).rstrip()  # get first line
        rewrite.append(l)
        while lines:
            print(l)
            # look for HTML comment, if starting, skip line.
            # XXX this is braindead!  it doesn't look for the end
            # so please put ending of comments on one line:
            # <!-- line 1 comment -->
            # <!-- line 2 comment -->
            if l.startswith('<!--'):
                print ("skipping comment", l)
                continue
            # expect get heading
            assert l.startswith('#'), ("# not found in line %s" % l)

            # whitespace expected
            l = lines.pop(0).strip()
            print(repr(l))
            assert len(l) == 0, ("blank line not found %s" % l)
            rewrite.append(l)

            # Form expected
            l = lines.pop(0).strip()
            assert l.endswith('-Form'), ("line with -Form expected %s" % l)
            rewrite.append(l)

            # whitespace expected
            l = lines.pop(0).strip()
            assert len(l) == 0, ("blank line not found %s" % l)
            rewrite.append(l)

            # get list of opcodes
            while True:
                l = lines.pop(0).strip()
                rewrite.append(l)
                if len(l) == 0:
                    break
                assert l.startswith('*'), ("* not found in line %s" % l)

            rewrite.append("Pseudo-code:")
            rewrite.append("")
            # get pseudocode
            while True:
                l = lines.pop(0).rstrip()
                rewrite.append(l)
                if len(l) == 0:
                    break
                assert l.startswith('    '), ("4spcs not found in line %s" % l)

            # "Special Registers Altered" expected
            l = lines.pop(0).rstrip()
            assert l.startswith("Special"), ("special not found %s" % l)
            rewrite.append(l)

            # whitespace expected
            l = lines.pop(0).strip()
            assert len(l) == 0, ("blank line not found %s" % l)
            rewrite.append(l)

            # get special regs
            while lines:
                l = lines.pop(0).rstrip()
                rewrite.append(l)
                if len(l) == 0:
                    break
                assert l.startswith('    '), ("4spcs not found in line %s" % l)

            # expect and drop whitespace
            while lines:
                l = lines.pop(0).rstrip()
                rewrite.append(l)
                if len(l) != 0:
                    break

        return rewrite

    def read_file(self, fname):
        pagename = fname.split('.')[0]
        fname = os.path.join(get_isa_dir(), fname)
        with open(fname) as f:
            lines = f.readlines()

        # set up dict with current page name
        d = {'page': pagename}

        # line-by-line lexer/parser, quite straightforward: pops one
        # line off the list and checks it.  nothing complicated needed,
        # all sections are mandatory so no need for a full LALR parser.

        l = lines.pop(0).rstrip()  # get first line
        while lines:
            print(l)
            # expect get heading
            assert l.startswith('#'), ("# not found in line %s" % l)
            d['desc'] = l[1:].strip()

            # whitespace expected
            l = lines.pop(0).strip()
            print(repr(l))
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
                if len(l) == 0:
                    break
                assert l.startswith('*'), ("* not found in line %s" % l)
                l = l[1:].split(' ')  # lose star
                l = filter(lambda x: len(x) != 0, l)  # strip blanks
                li.append(list(l))
            opcodes = li

            # "Pseudocode" expected
            l = lines.pop(0).rstrip()
            assert l.startswith("Pseudo-code:"), ("pseudocode found %s" % l)

            # whitespace expected
            l = lines.pop(0).strip()
            print(repr(l))
            assert len(l) == 0, ("blank line not found %s" % l)

            # get pseudocode
            li = []
            while True:
                l = lines.pop(0).rstrip()
                if len(l) == 0:
                    break
                assert l.startswith('    '), ("4spcs not found in line %s" % l)
                l = l[4:]  # lose 4 spaces
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
                if len(l) == 0:
                    break
                assert l.startswith('    '), ("4spcs not found in line %s" % l)
                l = l[4:]  # lose 4 spaces
                li.append(l)
            d['sregs'] = li

            # add in opcode
            for o in opcodes:
                self.add_op(o, d)

            # expect and drop whitespace
            while lines:
                l = lines.pop(0).rstrip()
                if len(l) != 0:
                    break

    def add_op(self, o, d):
        opcode, regs = o[0], o[1:]
        op = copy(d)
        op['regs'] = regs
        if len(regs) != 0:
            regs[0] = regs[0].split(",")
        op['opcode'] = opcode
        self.instr[opcode] = Ops(**op)

        # create list of instructions by form
        form = op['form']
        fl = self.forms.get(form, [])
        self.forms[form] = fl + [opcode]

        # create list of instructions by page
        page = op['page']
        pl = self.page.get(page, [])
        self.page[page] = pl + [opcode]

    def pprint_ops(self):
        for k, v in self.instr.items():
            print("# %s %s" % (v.opcode, v.desc))
            print("Form: %s Regs: %s" % (v.form, v.regs))
            print('\n'.join(map(lambda x: "    %s" % x, v.pcode)))
            print("Specials")
            print('\n'.join(map(lambda x: "    %s" % x, v.sregs)))
            print()
        for k, v in isa.forms.items():
            print(k, v)


if __name__ == '__main__':
    isa = ISA()
    isa.pprint_ops()
    # example on how to access cmp regs:
    print ("cmp regs:", isa.instr["cmp"].regs)
