from nmigen import *
from nmigen.back import rtlil


sr_set = Signal(3)
sr_clr = Signal(3)
q = Signal(3)

m = Module()
m.submodules += Instance("$sr",
    p_WIDTH=3,
    p_SET_POLARITY=1,
    p_CLR_POLARITY=1,
	i_SET=sr_set,
	i_CLR=sr_clr,
	o_Q=q)
print(rtlil.convert(m, ports=[sr_set, sr_clr, q]))
