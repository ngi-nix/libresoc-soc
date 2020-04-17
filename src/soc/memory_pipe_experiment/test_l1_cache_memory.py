from nmigen.back import rtlil
from nmigen.back.pysim import Simulator, Delay
import unittest
from .config import MemoryPipeConfig
from .l1_cache_memory import L1CacheMemory


class TestL1CacheMemory(unittest.TestCase):
    def test_l1_cache_memory(self):
        config = MemoryPipeConfig(bytes_per_cache_line=4,
                                  l1_way_count=8,
                                  l1_set_count=32)
        base_name = "test_l1_cache_memory"
        with self.subTest(part="synthesize"):
            dut = L1CacheMemory(config)
            vl = rtlil.convert(dut)
            with open(f"{base_name}.il", "w") as f:
                f.write(vl)
        dut = L1CacheMemory(config)
        sim = Simulator(dut)
        clock_period = 1e-6
        sim.add_clock(clock_period)

        def process():
            for set_index in range(config.l1_set_count):
                for way_index in range(config.l1_way_count):
                    yield dut.set_index.eq(set_index)
                    yield dut.way_index.eq(way_index)
                    yield dut.write_enable.eq(1)
                    yield dut.write_byte_en.eq(0xF)
                    write_data = set_index * 0x10 + way_index
                    write_data *= 0x00010001
                    write_data ^= 0x80808080
                    yield dut.write_data.eq(write_data)
                    yield
                    yield dut.set_index.eq(set_index)
                    yield dut.way_index.eq(way_index)
                    yield dut.write_enable.eq(0)
                    yield
                    yield Delay(clock_period / 10)
                    yield dut.set_index.eq(set_index + 1)
                    yield dut.way_index.eq(way_index + 1)
                    yield Delay(clock_period / 10)
                    read_data = (yield dut.read_data)
                    self.assertEqual(read_data, write_data)

        sim.add_sync_process(process)
        with sim.write_vcd(vcd_file=open(f"{base_name}.vcd", "w"),
                           gtkw_file=open(f"{base_name}.gtkw", "w")):
            sim.run()
