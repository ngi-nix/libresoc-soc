# License: LPGLv3
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
# Copyright (C) 2020 Luke Kenneth Casson Leighton <lkcl@lkcl.net>

import tempfile
import subprocess
import struct


def get_assembled_instruction(instruction, bigendian=False):
    if bigendian:
        endian_fmt = "elf64-big"
        obj_fmt = "-be"
    else:
        endian_fmt = "elf64-little"
        obj_fmt = "-le"
    with tempfile.NamedTemporaryFile(suffix=".o") as outfile:
        args = ["powerpc64-linux-gnu-as",
                obj_fmt,
                "-o",
                outfile.name]
        p = subprocess.Popen(args, stdin=subprocess.PIPE)
        p.communicate(instruction.encode('utf-8'))
        assert(p.wait() == 0)

        with tempfile.NamedTemporaryFile(suffix=".bin") as binfile:
            args = ["powerpc64-linux-gnu-objcopy",
                    "-I", endian_fmt,
                    "-O", "binary",
                    outfile.name,
                    binfile.name]
            subprocess.check_output(args)
            binary = struct.unpack('>i', binfile.read(4))[0]
            return binary
