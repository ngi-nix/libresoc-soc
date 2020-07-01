"""ConfigureableLoadStoreUnit and ConfigMemoryPortInterface

allows the type of LoadStoreUnit to be run-time selectable

this allows the same code to be used for both small unit tests
as well as larger ones and so on, without needing large amounts
of unnecessarily-duplicated code
"""
from soc.experiment.lsmem import TestMemLoadStoreUnit
from soc.bus.test.test_minerva import TestSRAMBareLoadStoreUnit
from soc.experiment.pi2ls import Pi2LSUI
from soc.experiment.pimem import TestMemoryPortInterface

class ConfigLoadStoreUnit:
    def __init__(self, pspec):
        lsidict = {'testmem': TestMemLoadStoreUnit,
                   'test_bare_wb': TestSRAMBareLoadStoreUnit,
                   #'test_cache_wb': TestCacheLoadStoreUnit
                  }
        lsikls = lsidict[pspec.ldst_ifacetype]
        self.lsi = lsikls(pspec)


class ConfigMemoryPortInterface:
    def __init__(self, pspec):
        if pspec.ldst_ifacetype == 'testpi':
            self.pi = TestMemoryPortInterface(addrwid=pspec.addr_wid, # adr bus
                                              regwid=pspec.reg_wid) # data bus
            return
        self.lsmem = ConfigLoadStoreUnit(pspec)
        self.pi = Pi2LSUI("mem", lsui=self.lsmem.lsi,
                          addr_wid=pspec.addr_wid, # address range
                          mask_wid=pspec.mask_wid, # cache line range
                          data_wid=pspec.reg_wid)  # data bus width
