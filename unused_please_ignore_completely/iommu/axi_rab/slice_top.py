# // Copyright 2018 ETH Zurich and University of Bologna.
# // Copyright and related rights are licensed under the Solderpad Hardware
# // License, Version 0.51 (the "License"); you may not use this file except in
# // compliance with the License.  You may obtain a copy of the License at
# // http://solderpad.org/licenses/SHL-0.51. Unless required by applicable law
# // or agreed to in writing, software, hardware and materials distributed under
# // this License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# // CONDITIONS OF ANY KIND, either express or implied. See the License for the
# // specific language governing permissions and limitations under the License.

# this file has been generated by sv2nmigen

from nmigen import Signal, Module, Const, Cat, Elaboratable
import rab_slice
import coreconfig

#
# module slice_top
# //#(
#  //  parameter N_SLICES        = 16,
#  //  parameter N_REGS          = 4*N_SLICES,
#   // parameter ADDR_WIDTH_PHYS = 40,
#   // parameter ADDR_WIDTH_VIRT = 32
#  //  )
#   (
#    input   logic   [N_REGS-1:0] [63:0] int_cfg_regs,
#    input   logic                       int_rw,
#    input   logic [ADDR_WIDTH_VIRT-1:0] int_addr_min,
#    input   logic [ADDR_WIDTH_VIRT-1:0] int_addr_max,
#    input   logic                       multi_hit_allow,
#    output  logic                       multi_hit,
#    output  logic        [N_SLICES-1:0] prot,
#    output  logic        [N_SLICES-1:0] hit,
#    output  logic                       cache_coherent,
#    output  logic [ADDR_WIDTH_PHYS-1:0] out_addr
#  );
#


class slice_top(Elaboratable):

    def __init__(self):
        # FIXME self.int_cfg_regs = Signal()  # input
        self.params = coreconfig.CoreConfig() # rename ?
        self.int_rw = Signal()  # input
        self.int_addr_min = Signal(self.params.ADDR_WIDTH_VIRT)  # input
        self.int_addr_max = Signal(self.params.ADDR_WIDTH_VIRT)  # input
        self.multi_hit_allow = Signal()  # input
        self.multi_hit = Signal()  # output
        self.prot = Signal(self.params.N_SLICES)  # output
        self.hit = Signal(self.params.N_SLICES)  # output
        self.cache_coherent = Signal()  # output
        self.out_addr = Signal(self.params.ADDR_WIDTH_PHYS)  # output

    def elaborate(self, platform=None):
        m = Module()

        first_hit = Signal()

        for i in range(self.params.N_SLICES):
            # TODO pass params / core config here
            u_slice = rab_slice.rab_slice(self.params)
            setattr(m.submodules, "u_slice%d" % i, u_slice)
            # TODO set param and connect ports

        # In case of a multi hit, the lowest slice with a hit is selected.
        # TODO always_comb begin : HIT_CHECK
        m.d.comb += [
            first_hit.eq(0),
            self.multi_hit.eq(0),
            self.out_addr.eq(0),
            self.cache_coherent.eq(0)]

        for j in range(self.params.N_SLICES):
            with m.If(self.hit[j] == 1):
                with m.If(first_hit == 1):
                    with m.If(self.multi_hit_allow == 0):
                        m.d.comb += [self.multi_hit.eq(1)]
                with m.Elif(first_hit == 1):
                    m.d.comb += [first_hit.eq(1)
                                 # only output first slice that was hit
                                 # SV self.out_addr.eq(slice_out_addr[ADDR_WIDTH_PHYS*j + : ADDR_WIDTH_PHYS]),
                                 # SV self.cache_coherent.eq(int_cfg_regs[4*j+3][3]),
                                 ]
        return m

  # TODO translate generate statement


"""
  logic [ADDR_WIDTH_PHYS*N_SLICES-1:0]  slice_out_addr;

  generate
    for ( i=0; i<N_SLICES; i++ )
      begin
        rab_slice
          #(
            .ADDR_WIDTH_PHYS ( ADDR_WIDTH_PHYS ),
            .ADDR_WIDTH_VIRT ( ADDR_WIDTH_VIRT )
            )
          u_slice
          (
            .cfg_min       ( int_cfg_regs[4*i]  [ADDR_WIDTH_VIRT-1:0]                              ),
            .cfg_max       ( int_cfg_regs[4*i+1][ADDR_WIDTH_VIRT-1:0]                              ),
            .cfg_offset    ( int_cfg_regs[4*i+2][ADDR_WIDTH_PHYS-1:0]                              ),
            .cfg_wen       ( int_cfg_regs[4*i+3][2]                                                ),
            .cfg_ren       ( int_cfg_regs[4*i+3][1]                                                ),
            .cfg_en        ( int_cfg_regs[4*i+3][0]                                                ),
            .in_trans_type ( int_rw                                                                ),
            .in_addr_min   ( int_addr_min                                                          ),
            .in_addr_max   ( int_addr_max                                                          ),
            .out_addr      ( slice_out_addr[ADDR_WIDTH_PHYS*i+ADDR_WIDTH_PHYS-1:ADDR_WIDTH_PHYS*i] ),
            .out_prot      ( prot[i]                                                               ),
            .out_hit       ( hit[i]                                                                )
          );
     end
  endgenerate

  // In case of a multi hit, the lowest slice with a hit is selected.
  always_comb begin : HIT_CHECK
    first_hit      =  0;
    multi_hit      =  0;
    out_addr       = '0;
    cache_coherent =  0;
    for (j = 0; j < N_SLICES; j++) begin
      if (hit[j] == 1'b1) begin
        if (first_hit == 1'b1) begin
          if (multi_hit_allow == 1'b0) begin
            multi_hit = 1'b1;
          end
        end else begin
          first_hit       = 1'b1;
          out_addr        = slice_out_addr[ADDR_WIDTH_PHYS*j +: ADDR_WIDTH_PHYS];
          cache_coherent  = int_cfg_regs[4*j+3][3];
        end
      end
    end
  end
"""

# sv 2 migen: TODO add translate code for generate statements and for loops inside always_comb
