#include <stdio.h>

#include "sr.cc"

cxxrtl_design::p_top top;

void step() {
	top.step();
	fprintf(stderr, "SET %d CLR %d Q %d\n",
	        top.p_sr__set.data[0], top.p_sr__clr.data[0], top.p_q.data[0]);
}

int main() {
	step();

	top.p_sr__set = value<3>{3u};
	step(); // set bits 0 & 1

	top.p_sr__set = value<3>{0u};
	top.p_sr__clr = value<3>{1u};
	step(); // clear bit 0

	top.p_sr__clr = value<3>{0u};
	step(); // retain latched value

	top.p_sr__set = value<3>{2u};
	top.p_sr__clr = value<3>{2u};
	step(); // clear bit 1, since CLR has priority over SET

	return 0;
}
