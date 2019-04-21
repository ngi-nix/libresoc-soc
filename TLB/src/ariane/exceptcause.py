from nmigen import Const

INSTR_ADDR_MISALIGNED = Const(0, 64)
INSTR_ACCESS_FAULT    = Const(1, 64)
ILLEGAL_INSTR         = Const(2, 64)
BREAKPOINT            = Const(3, 64)
LD_ADDR_MISALIGNED    = Const(4, 64)
LD_ACCESS_FAULT       = Const(5, 64)
ST_ADDR_MISALIGNED    = Const(6, 64)
ST_ACCESS_FAULT       = Const(7, 64)
ENV_CALL_UMODE        = Const(8, 64)  # environment call from user mode
ENV_CALL_SMODE        = Const(9, 64)  # environment call from supervisor mode
ENV_CALL_MMODE        = Const(11, 64) # environment call from machine mode
INSTR_PAGE_FAULT      = Const(12, 64) # Instruction page fault
LOAD_PAGE_FAULT       = Const(13, 64) # Load page fault
STORE_PAGE_FAULT      = Const(15, 64) # Store page fault
