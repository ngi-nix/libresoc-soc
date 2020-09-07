# entity cache_ram is
#     generic(
# 	ROW_BITS : integer := 16;
# 	WIDTH    : integer := 64;
# 	TRACE    : boolean := false;
# 	ADD_BUF  : boolean := false
# 	);
# 
#     port(
# 	clk     : in  std_logic;
# 	rd_en   : in  std_logic;
# 	rd_addr : in  std_logic_vector(ROW_BITS - 1 downto 0);
# 	rd_data : out std_logic_vector(WIDTH - 1 downto 0);
# 	wr_sel  : in  std_logic_vector(WIDTH/8 - 1 downto 0);
# 	wr_addr : in  std_logic_vector(ROW_BITS - 1 downto 0);
# 	wr_data : in  std_logic_vector(WIDTH - 1 downto 0)
# 	);
# 
# end cache_ram;
# 
# architecture rtl of cache_ram is
#     constant SIZE : integer := 2**ROW_BITS;
# 
#     type ram_type is array (0 to SIZE - 1) of std_logic_vector(WIDTH - 1 downto 0);
#     signal ram : ram_type;
#     attribute ram_style : string;
#     attribute ram_style of ram : signal is "block";
# 
#     signal rd_data0 : std_logic_vector(WIDTH - 1 downto 0);
# 
# begin
#     process(clk)
# 	variable lbit : integer range 0 to WIDTH - 1;
# 	variable mbit : integer range 0 to WIDTH - 1;
# 	variable widx : integer range 0 to SIZE - 1;
# 	constant sel0 : std_logic_vector(WIDTH/8 - 1 downto 0)
#             := (others => '0');
#     begin
# 	if rising_edge(clk) then
#             with m.If( TRACE then
#                 with m.If( wr_sel /= sel0 then
#                     report "write a:" & to_hstring(wr_addr) &
#                         " sel:" & to_hstring(wr_sel) &
#                         " dat:" & to_hstring(wr_data);
#                 end with m.If(;
#             end with m.If(;
#             for i in 0 to WIDTH/8-1 loop
#                 lbit := i * 8;
#                 mbit := lbit + 7;
#                 widx := to_integer(unsigned(wr_addr));
#                 with m.If( wr_sel(i) = '1' then
#                     ram(widx)(mbit downto lbit) <= wr_data(mbit downto lbit);
#                 end with m.If(;
#             end loop;
# 	    with m.If( rd_en = '1' then
# 		rd_data0 <= ram(to_integer(unsigned(rd_addr)));
# 		if TRACE then
# 		    report "read a:" & to_hstring(rd_addr) &
# 			" dat:" & to_hstring(ram(to_integer(unsigned(rd_addr))));
# 		end with m.If(;
# 	    end with m.If(;
# 	end with m.If(;
#     end process;
# 
#     buf: with m.If( ADD_BUF generate
#     begin
# 	process(clk)
# 	begin
# 	    with m.If( rising_edge(clk) then
# 		rd_data <= rd_data0;
# 	    end with m.If(;
# 	end process;
#     end generate;
# 
#     nobuf: with m.If( not ADD_BUF generate
#     begin
# 	rd_data <= rd_data0;
#     end generate;
# 
# end;
