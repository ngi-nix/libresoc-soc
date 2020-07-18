demo: build run

build:
	python3 sr.py >sr.il
	yosys sr.il -o sr.cc
	g++ `yosys-config --cxxflags` sr_driver.cc -o sr

run:
	./sr

clean:
	rm sr sr.d sr.il sr.cc
