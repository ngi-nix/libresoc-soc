"""ConfigureableFetchUnit and ConfigMemoryPortInterface

allows the type of FetchUnit to be run-time selectable

this allows the same code to be used for both small unit tests
as well as larger ones and so on, without needing large amounts
of unnecessarily-duplicated code
"""
from soc.experiment.imem import TestMemFetchUnit
from soc.bus.test.test_minerva import TestSRAMBareFetchUnit
from soc.minerva.units.fetch import BareFetchUnit


class ConfigFetchUnit:
    def __init__(self, pspec):
        fudict = {'testmem': TestMemFetchUnit,
                   'test_bare_wb': TestSRAMBareFetchUnit,
                   'bare_wb': BareFetchUnit,
                   #'test_cache_wb': TestCacheFetchUnit
                  }
        fukls = fudict[pspec.imem_ifacetype]
        self.fu = fukls(pspec)

