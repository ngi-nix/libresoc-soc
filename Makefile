PYTHON3 ?= "python3"

.PHONY: help Makefile gitupdate install run_sim test htmlupload

gitupdate:
	git submodule init
	git submodule update --recursive

install:
	python3 setup.py develop # yes, develop, not install
	python3 src/soc/decoder/pseudo/pywriter.py

run_sim: install
	python3 src/soc/simple/issuer_verilog.py src/soc/litex/florent/libresoc/libresoc.v
	python3 src/soc/litex/florent/sim.py --cpu=libresoc

test: install
	python3 setup.py test # could just run nosetest3...

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

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	mkdir -p "$(SOURCEDIR)"/src/gen
	sphinx-apidoc --ext-autodoc -o "$(SOURCEDIR)"/src/gen ./src/soc
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

htmlupload: clean html
	rsync -HPavz --delete build/html/* \
        libre-soc.org:/var/www/libre-soc.org/docs/soc/
