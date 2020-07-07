"""POWER Program

takes powerpc assembly instructions and turns them into LE/BE binary
data.  calls powerpc64-linux-gnu-as, ld and objcopy to do so.
"""

import tempfile
import subprocess
import struct
import os
import sys

filedir = os.path.dirname(os.path.realpath(__file__))
memmap = os.path.join(filedir, "memmap")

bigendian = True
endian_fmt = "elf64-big"
obj_fmt = "-be"


class Program:
    def __init__(self, instructions):
        if isinstance(instructions, str): # filename
            self.binfile = open(instructions, "rb")
            self.assembly = '' # noo disassemble number fiiive
            print ("program", self.binfile)
        else:
            if isinstance(instructions, list):
                instructions = '\n'.join(instructions)
            self.assembly = instructions + '\n' # plus final newline
            self._assemble()
        self._instructions = list(self._get_instructions())

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def _get_binary(self, elffile):
        self.binfile = tempfile.NamedTemporaryFile(suffix=".bin")
        args = ["powerpc64-linux-gnu-objcopy",
                "-O", "binary",
                "-I", endian_fmt,
                elffile.name,
                self.binfile.name]
        subprocess.check_output(args)

    def _link(self, ofile):
        with tempfile.NamedTemporaryFile(suffix=".elf") as elffile:
            args = ["powerpc64-linux-gnu-ld",
                    "-o", elffile.name,
                    "-T", memmap,
                    ofile.name]
            subprocess.check_output(args)
            self._get_binary(elffile)

    def _assemble(self):
        with tempfile.NamedTemporaryFile(suffix=".o") as outfile:
            args = ["powerpc64-linux-gnu-as",
                    '-mpower9',
                    obj_fmt,
                    "-o",
                    outfile.name]
            p = subprocess.Popen(args, stdin=subprocess.PIPE)
            p.communicate(self.assembly.encode('utf-8'))
            if p.wait() != 0:
                print("Error in program:")
                print(self.assembly)
                sys.exit(1)
            self._link(outfile)

    def _get_instructions(self):
        while True:
            data = self.binfile.read(4)
            if not data:
                break
            yield struct.unpack('<i', data)[0]

    def generate_instructions(self):
        yield from self._instructions

    def reset(self):
        self.binfile.seek(0)

    def size(self):
        curpos = self.binfile.tell()
        self.binfile.seek(0, 2)  # Seek to end of file
        size = self.binfile.tell()
        self.binfile.seek(curpos, 0)
        return size

    def close(self):
        self.binfile.close()
