	lis 1, 0xdead
	ori 1, 1, 0xbeef
	lis 2, 0x2000
	ori 2, 2, 0x0100
	std 1, 0(2)
	lhz 1, 4(2)
