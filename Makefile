gitupdate:
	git submodule init
	git submodule update --recursive

install:
	python3 setup.py develop # yes, develop, not install

test:
	python3 setup.py test # could just run nosetest3...
