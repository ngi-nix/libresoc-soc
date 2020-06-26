"""ConfigureableLoadStoreUnit

allows the type of LoadStoreUnit to be run-time selectable

"""
from soc.experiment.pimem import TestMemoryLoadStoreUnit
from soc.bus.test.test_minerva import TestSRAMBareLoadStoreUnit


class ConfigureableLoadStoreUnit:
    def __init__(self, pspec):
        lsidict = {'testmem': TestMemoryLoadStoreUnit,
                   'test_bare_wb': TestBareLoadStoreUnit,
                   #'test_cache_wb': TestCacheLoadStoreUnit
                  }
        lsikls = lsidict[pspec.ldst_ifacetype]
        self.lsi = lsikls(addr_wid=pspec.addr_wid, # address range
                          mask_wid=pspec.mask_wid, # cache line range
                          data_wid=pspec.reg_wid)  # data bus width

