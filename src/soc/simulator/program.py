"""POWER Program

takes powerpc assembly instructions and turns them into LE/BE binary
data.  calls powerpc64-linux-gnu-as, ld and objcopy to do so.
"""
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

import tempfile
import subprocess
import struct
import os
import sys
from io import BytesIO


filedir = os.path.dirname(os.path.realpath(__file__))
memmap = os.path.join(filedir, "memmap")


class Program:
    def __init__(self, instructions, bigendian):
        self.bigendian = bigendian
        if self.bigendian:
            self.endian_fmt = "elf64-big"
            self.obj_fmt = "-be"
            self.ld_fmt = "-EB"
        else:
            self.ld_fmt = "-EL"
            self.endian_fmt = "elf64-little"
            self.obj_fmt = "-le"

        if isinstance(instructions, bytes):  # actual bytes
            self.binfile = BytesIO(instructions)
            self.binfile.name = "assembly"
            self.assembly = ''  # noo disassemble number fiiive
        elif isinstance(instructions, str):  # filename
            # read instructions into a BytesIO to avoid "too many open files"
            with open(instructions, "rb") as f:
                b = f.read()
            self.binfile = BytesIO(b)
            self.assembly = ''  # noo disassemble number fiiive
            print("program", self.binfile)
        else:
            if isinstance(instructions, list):
                instructions = '\n'.join(instructions)
            self.assembly = instructions + '\n'  # plus final newline
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
                "-I", self.endian_fmt,
                elffile.name,
                self.binfile.name]
        subprocess.check_output(args)

    def _link(self, ofile):
        with tempfile.NamedTemporaryFile(suffix=".elf") as elffile:
            args = ["powerpc64-linux-gnu-ld",
                    self.ld_fmt,
                    "-o", elffile.name,
                    "-T", memmap,
                    ofile.name]
            subprocess.check_output(args)
            self._get_binary(elffile)

    def _assemble(self):
        with tempfile.NamedTemporaryFile(suffix=".o") as outfile:
            args = ["powerpc64-linux-gnu-as",
                    '-mpower9',
                    self.obj_fmt,
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
            yield struct.unpack('<I', data)[0]  # unsigned int

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
