"""ConfigureableLoadStoreUnit

allows the type of LoadStoreUnit to be run-time selectable

"""
from soc.experiment.pimem import TestMemoryLoadStoreUnit
from soc.minerva.units.loadstore import BareLoadStoreUnit, CacheLoadStoreUnit


class ConfigureableLoadStoreUnit:
    def __init__(self, pspec):
        lsidict = {'testmem': TestMemoryLoadStoreUnit,
                   'bare_wb': BareLoadStoreUnit,
                   'cache_wb': CacheLoadStoreUnit # TODO dcache parameters
                  }
        lsikls = lsidict[pspec.ldst_ifacetype]
        self.lsi = lsikls(addr_wid=pspec.addr_wid,
                          mask_wid=pspec.mask_wid, # cache line range
                          data_wid=pspec.reg_wid)

