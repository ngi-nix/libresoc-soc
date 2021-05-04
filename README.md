# About

The main SOC portion of Libre-SOC. A quad-core open source SOC with a 3D GPU,
VPU, and using Libre-licensed design cells.

Libre-SOC is Libre down to the VLSI Cells, thanks to Chips4Makers FlexLib
and Sorbonne University lip6.fr

# [Documentation](https://libre-soc.org/docs/)

# Installation

Best done using the dev-env-setup scripts:
https://git.libre-soc.org/?p=dev-env-setup.git;a=summary

    make install
    make test # optional (ish)

# Running Simulator tests

qemu and gdb for Power 64 are required.  qemu can be installed with
"apt-get install qemu-system-ppc64", however gdb needs compiling from
source.  Obtain the latest tarball, unpack it, then:

    cd gdb-9.1 (or other location)
    mkdir build
    cd build
     ../configure --srcdir=.. --host=x86_64-linux --target=powerpc64-linux-gnu
    make -j16
    make install

You will need to have installed the powerpc gnu gcc cross-compiler for
this to work:

    apt-get install gcc-9-powerpc64-linux-gnu

Or, use this dev-env-script:
https://git.libre-soc.org/?p=dev-env-setup.git;a=blob;f=ppc64-gdb-gcc;hb=HEAD
