import tempfile
import subprocess
import struct
import os

filedir = os.path.dirname(os.path.realpath(__file__))
memmap = os.path.join(filedir, "memmap")

bigendian = True
endian_fmt = "elf64-big"
obj_fmt = "-be"

class Program:
    def __init__(self, instructions):
        if isinstance(instructions, list):
            instructions = '\n'.join(instructions)
        self.assembly = instructions
        self._assemble()

    def _get_binary(self, elffile):
        self.binfile = tempfile.NamedTemporaryFile(suffix=".bin")
        #self.binfile = open("kernel.bin", "wb+")
        args = ["powerpc64-linux-gnu-objcopy",
                "-O", "binary",
                "-I", endian_fmt,
                elffile.name,
                self.binfile.name]
        subprocess.check_output(args)

    def _link(self, ofile):
        with tempfile.NamedTemporaryFile(suffix=".elf") as elffile:
        #with open("kernel.elf", "wb+") as elffile:
            args = ["powerpc64-linux-gnu-ld",
                    "-o", elffile.name,
                    "-T", memmap,
                    ofile.name]
            subprocess.check_output(args)
            self._get_binary(elffile)

    def _assemble(self):
        with tempfile.NamedTemporaryFile(suffix=".o") as outfile:
            args = ["powerpc64-linux-gnu-as",
                    obj_fmt,
                    "-o",
                    outfile.name]
            p = subprocess.Popen(args, stdin=subprocess.PIPE)
            p.communicate(self.assembly.encode('utf-8'))
            assert(p.wait() == 0)
            self._link(outfile)

    def generate_instructions(self):
        while True:
            data = self.binfile.read(4)
            if not data:
                break
            yield struct.unpack('<i', data)[0]
