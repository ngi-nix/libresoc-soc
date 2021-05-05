# About

The main SOC portion of Libre-SOC. A quad-core open source SOC with a 3D GPU,
VPU, and using Libre-licensed design cells.

Libre-SOC is Libre down to the VLSI Cells, thanks to Chips4Makers FlexLib
and Sorbonne University lip6.fr

# Documentation

See https://libre-soc.org/docs/

# Installation

Best done using the dev-env-setup scripts:
https://git.libre-soc.org/?p=dev-env-setup.git;a=summary

    make install
    make test # optional (ish)

# Running Simulator tests

qemu and gdb for Power 64 are required.  qemu can be installed with
"apt-get install qemu-system-ppc64", however gdb needs compiling from
source.  The simplest way is to use this dev-env-script:

https://git.libre-soc.org/?p=dev-env-setup.git;a=blob;f=ppc64-gdb-gcc;hb=HEAD
