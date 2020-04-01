# Installation

    make update
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

