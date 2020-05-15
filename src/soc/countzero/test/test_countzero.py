# https://github.com/antonblanchard/microwatt/blob/master/countzero_tb.vhdl
from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.countzero.countzero import ZeroCounter


class ZeroCounterTestCase(FHDLTestCase):
    def test_zerocounter(self):
        m = Module()
        comb = m.d.comb
        m.submodules.dut = dut = ZeroCounter()

        sim = Simulator(m)
        # sim.add_clock(1e-6)

        def process():
            print("test zero input")
            yield dut.rs_i.eq(0)
            yield dut.is_32bit_i.eq(0)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            # assert result = x"0000000000000040"
            result = yield dut.result_o
            # report "bad cntlzd 0 = " & to_hstring(result);
            assert(result == 0x40)
            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            # report "bad cntlzd 0 = " & to_hstring(result);
            assert(result == 0x40)
            yield dut.is_32bit_i.eq(1)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            # report "bad cntlzw 0 = " & to_hstring(result);
            assert(result == 0x20)
            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            # report "bad cntlzw 0 = " & to_hstring(result);
            assert(result == 0x20)
            # TODO next tests

            yield dut.rs_i.eq(0b00010000)
            yield dut.is_32bit_i.eq(0)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 4, "result %d" % result

            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 59, "result %d" % result

            yield dut.is_32bit_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 27, "result %d" % result

            yield dut.rs_i.eq(0b1100000100000000)
            yield dut.is_32bit_i.eq(0)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 8, "result %d" % result

            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 55, "result %d" % result

            yield dut.is_32bit_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 23, "result %d" % result


        sim.add_process(process)  # or sim.add_sync_process(process), see below

        # run test and write vcd
        fn = "genullnau"
        with sim.write_vcd(fn+".vcd", fn+".gtkw", traces=dut.ports()):
            sim.run()

    # cntlzd_w
    # cnttzd_w


if __name__ == "__main__":
    unittest.main()

"""
stim_process: process
        variable r: std_ulogic_vector(63 downto 0);
    begin
        -- test with input = 0
        report "test zero input";
        rs <= (others => '0');
        is_32bit <= '0';
        count_right <= '0';
        wait for clk_period;
        assert result = x"0000000000000040"
            report "bad cntlzd 0 = " & to_hstring(result);
        count_right <= '1';
        wait for clk_period;
        assert result = x"0000000000000040"
            report "bad cnttzd 0 = " & to_hstring(result);
        is_32bit <= '1';
        count_right <= '0';
        wait for clk_period;
        assert result = x"0000000000000020"
            report "bad cntlzw 0 = " & to_hstring(result);
        count_right <= '1';
        wait for clk_period;
        assert result = x"0000000000000020"
            report "bad cnttzw 0 = " & to_hstring(result);

        report "test cntlzd/w";
        count_right <= '0';
        for j in 0 to 100 loop
            r := pseudorand(64);
            r(63) := '1';
            for i in 0 to 63 loop
                rs <= r;
                is_32bit <= '0';
                wait for clk_period;
                assert to_integer(unsigned(result)) = i
                    report "bad cntlzd " & to_hstring(rs) & " -> " & to_hstring(result);
                rs <= r(31 downto 0) & r(63 downto 32);
                is_32bit <= '1';
                wait for clk_period;
                if i < 32 then
                    assert to_integer(unsigned(result)) = i
                        report "bad cntlzw " & to_hstring(rs) & " -> " & to_hstring(result);
                else
                    assert to_integer(unsigned(result)) = 32
                        report "bad cntlzw " & to_hstring(rs) & " -> " & to_hstring(result);
                end if;
                r := '0' & r(63 downto 1);
            end loop;
        end loop;

        report "test cnttzd/w";
        count_right <= '1';
        for j in 0 to 100 loop
            r := pseudorand(64);
            r(0) := '1';
            for i in 0 to 63 loop
                rs <= r;
                is_32bit <= '0';
                wait for clk_period;
                assert to_integer(unsigned(result)) = i
                    report "bad cnttzd " & to_hstring(rs) & " -> " & to_hstring(result);
                is_32bit <= '1';
                wait for clk_period;
                if i < 32 then
                    assert to_integer(unsigned(result)) = i
                        report "bad cnttzw " & to_hstring(rs) & " -> " & to_hstring(result);
                else
                    assert to_integer(unsigned(result)) = 32
                        report "bad cnttzw " & to_hstring(rs) & " -> " & to_hstring(result);
                end if;
                r := r(62 downto 0) & '0';
            end loop;
        end loop;

        assert false report "end of test" severity failure;
        wait;
    end process;
"""
