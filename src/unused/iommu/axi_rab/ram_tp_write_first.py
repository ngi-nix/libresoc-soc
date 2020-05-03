# // Copyright 2018 ETH Zurich and University of Bologna.
# // Copyright and related rights are licensed under the Solderpad Hardware
# // License, Version 0.51 (the "License"); you may not use this file except in
# // compliance with the License.  You may obtain a copy of the License at
# // http://solderpad.org/licenses/SHL-0.51. Unless required by applicable law
# // or agreed to in writing, software, hardware and materials distributed under
# // this License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# // CONDITIONS OF ANY KIND, either express or implied. See the License for the
# // specific language governing permissions and limitations under the License.
#
# /*
# * ram_tp_write_first
# *
# * This code implements a parameterizable two-port memory. Port 0 can read and
# * write while Port 1 can read only. Xilinx Vivado will infer a BRAM in
# * "write first" mode, i.e., upon a read and write to the same address, the
# * new value is read. Note: Port 1 outputs invalid data in the cycle after
# * the write when reading the same address.
# *
# * For more information, see Xilinx PG058 Block Memory Generator Product Guide.
# */

from nmigen import Signal, Module, Const, Cat, Elaboratable
from nmigen import Memory

import math
#
# module ram_tp_write_first
#  #(
ADDR_WIDTH = 10
DATA_WIDTH = 36
#  )
#  (
#    input                   clk,
#    input                   we,
#    input  [ADDR_WIDTH-1:0] addr0,
#    input  [ADDR_WIDTH-1:0] addr1,
#    input  [DATA_WIDTH-1:0] d_i,
#    output [DATA_WIDTH-1:0] d0_o,
#    output [DATA_WIDTH-1:0] d1_o
#  );


class ram_tp_write_first(Elaboratable):

    def __init__(self):
        self.we = Signal()               # input
        self.addr0 = Signal(ADDR_WIDTH)  # input
        self.addr1 = Signal(ADDR_WIDTH)  # input
        self.d_i = Signal(DATA_WIDTH)    # input
        self.d0_o = Signal(DATA_WIDTH)   # output
        self.d1_o = Signal(DATA_WIDTH)   # output

        DEPTH = int(math.pow(2, ADDR_WIDTH))
        self.ram = Memory(width=DATA_WIDTH, depth=DEPTH)

    #
    #  localparam DEPTH = 2**ADDR_WIDTH;
    #
    #  (* ram_style = "block" *) reg [DATA_WIDTH-1:0] ram[DEPTH];
    #                            reg [ADDR_WIDTH-1:0] raddr0;
    #                            reg [ADDR_WIDTH-1:0] raddr1;
    #
    #  always_ff @(posedge clk) begin
    #    if(we == 1'b1) begin
    #      ram[addr0] <= d_i;
    #    end
    #    raddr0 <= addr0;
    #    raddr1 <= addr1;
    #  end
    #
    #  assign d0_o = ram[raddr0];
    #  assign d1_o = ram[raddr1];
    #

    def elaborate(self, platform=None):
        m = Module()
        m.submodules.read_ram0 = read_ram0 = self.ram.read_port()
        m.submodules.read_ram1 = read_ram1 = self.ram.read_port()
        m.submodules.write_ram = write_ram = self.ram.write_port()

        # write port
        m.d.comb += write_ram.en.eq(self.we)
        m.d.comb += write_ram.addr.eq(self.addr0)
        m.d.comb += write_ram.data.eq(self.d_i)

        # read ports
        m.d.comb += read_ram0.addr.eq(self.addr0)
        m.d.comb += read_ram1.addr.eq(self.addr1)
        m.d.sync += self.d0_o.eq(read_ram0.data)
        m.d.sync += self.d1_o.eq(read_ram1.data)

        return m
