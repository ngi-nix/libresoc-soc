PYTHON3 ?= "python3"

.PHONY: help Makefile gitupdate install run_sim test htmlupload

gitupdate:
	git submodule init
	git submodule update --init --recursive --remote

mkpinmux:
	./mkpinmux.sh
	cp pinmux/ls180/ls180_pins.py src/soc/debug
	cp pinmux/ls180/ls180_pins.py src/soc/litex/florent/libresoc

install: gitupdate develop mkpinmux

# this is now actually part of openpower-isa repository
pywriter:
	echo "pywriter is part of openpower-isa, run that instead"

# this is now actually part of openpower-isa repository
svanalysis:
	echo "sv_analysis is part of openpower-isa, run that instead"

develop:
	python3 setup.py develop # yes, develop, not install

# build and run libresoc litex simulation
run_sim:
	python3 src/soc/simple/issuer_verilog.py --disable-svp64 \
			src/soc/litex/florent/libresoc/libresoc.v
	python3 src/soc/litex/florent/sim.py --cpu=libresoc

# and with test gpio (useful for XICS IRC testing)
testgpio_run_sim:
	python3 src/soc/simple/issuer_verilog.py \
			src/soc/litex/florent/libresoc/libresoc.v \
			--enable-testgpio
	python3 src/soc/litex/florent/sim.py --cpu=libresoc \
			--variant=standardjtagtestgpio

ls180_verilog_nopll:
	python3 src/soc/simple/issuer_verilog.py \
	        --debug=jtag --enable-core --disable-pll \
	        --enable-xics --disable-svp64 \
			src/soc/litex/florent/libresoc/libresoc.v

ls180_verilog:
	python3 src/soc/simple/issuer_verilog.py \
	        --debug=jtag --enable-core --enable-pll \
	        --enable-xics --disable-svp64 \
			src/soc/litex/florent/libresoc/libresoc.v

ls180_4k_verilog:
	python3 src/soc/simple/issuer_verilog.py \
	        --debug=jtag --enable-core --enable-pll \
	        --enable-xics --enable-sram4x4kblock --disable-svp64 \
			src/soc/litex/florent/libresoc/libresoc.v

# build the litex libresoc SoC without 4k SRAMs
ls180_verilog_build: ls180_verilog
	make -C soc/soc/litex/florent ls180

# build the litex libresoc SoC with 4k SRAMs
ls180_4ksram_verilog_build: ls180_4k_verilog
	make -C soc/soc/litex/florent ls1804k

# testing (usually done at install time)
test: install
	python3 setup.py test # could just run nosetest3...

pypiupload:
	$(PYTHON3) setup.py sdist upload

# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SPHINXPROJ    = Libre-SOC
SOURCEDIR     = .
BUILDDIR      = build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# copies all documentation to libre-soc (libre-soc admins only)
htmlupload: clean html
	rsync -HPavz --delete build/html/* \
        libre-soc.org:/var/www/libre-soc.org/docs/soc/

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	echo "catch-all falling through to sphinx for document building"
	mkdir -p "$(SOURCEDIR)"/src/gen
	sphinx-apidoc --ext-autodoc -o "$(SOURCEDIR)"/src/gen ./src/soc
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

