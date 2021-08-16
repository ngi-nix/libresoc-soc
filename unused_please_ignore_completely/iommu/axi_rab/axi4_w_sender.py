# this file has been generated by sv2nmigen

from nmigen import Signal, Module, Const, Cat, Elaboratable


class axi4_w_sender(Elaboratable):

    def __init__(self):
        self.axi4_aclk = Signal()  # input
        self.axi4_arstn = Signal()  # input
        self.s_axi4_wdata = Signal()  # input
        self.s_axi4_wvalid = Signal()  # input
        self.s_axi4_wready = Signal()  # output
        self.s_axi4_wstrb = Signal()  # input
        self.s_axi4_wlast = Signal()  # input
        self.s_axi4_wuser = Signal()  # input
        self.m_axi4_wdata = Signal()  # output
        self.m_axi4_wvalid = Signal()  # output
        self.m_axi4_wready = Signal()  # input
        self.m_axi4_wstrb = Signal()  # output
        self.m_axi4_wlast = Signal()  # output
        self.m_axi4_wuser = Signal()  # output

    def elaborate(self, platform=None):
        m = Module()
        m.d.comb += self.m_axi4_wdata.eq(self.s_axi4_wdata)
        m.d.comb += self.m_axi4_wstrb.eq(self.s_axi4_wstrb)
        m.d.comb += self.m_axi4_wlast.eq(self.s_axi4_wlast)
        m.d.comb += self.m_axi4_wuser.eq(self.s_axi4_wuser)
        m.d.comb += self.m_axi4_wvalid.eq(self.s_axi4_wvalid)
        m.d.comb += self.s_axi4_wready.eq(self.m_axi4_wready)
        return m

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
# module axi4_w_sender
#  #(
#    parameter AXI_DATA_WIDTH = 32,
#    parameter AXI_USER_WIDTH = 2
#  )
#  (
#    input                         axi4_aclk,
#    input                         axi4_arstn,
#
#    input    [AXI_DATA_WIDTH-1:0] s_axi4_wdata,
#    input                         s_axi4_wvalid,
#    output                        s_axi4_wready,
#    input  [AXI_DATA_WIDTH/8-1:0] s_axi4_wstrb,
#    input                         s_axi4_wlast,
#    input    [AXI_USER_WIDTH-1:0] s_axi4_wuser,
#
#    output   [AXI_DATA_WIDTH-1:0] m_axi4_wdata,
#    output                        m_axi4_wvalid,
#    input                         m_axi4_wready,
#    output [AXI_DATA_WIDTH/8-1:0] m_axi4_wstrb,
#    output                        m_axi4_wlast,
#    output   [AXI_USER_WIDTH-1:0] m_axi4_wuser
#  );
#
#  assign m_axi4_wdata  = s_axi4_wdata;
#  assign m_axi4_wstrb  = s_axi4_wstrb;
#  assign m_axi4_wlast  = s_axi4_wlast;
#  assign m_axi4_wuser  = s_axi4_wuser;
#
#  assign m_axi4_wvalid = s_axi4_wvalid;
#  assign s_axi4_wready = m_axi4_wready;
#
# endmodule
#
#