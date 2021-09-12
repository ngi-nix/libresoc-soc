# The license for this file is included in the `nix` directory next to this file.

{
  description = "FOSS CPU/GPU/VPU/SoC all in one, see https://libre-soc.org/";

  inputs.nixpkgs.url = "github:L-as/nixpkgs?ref=alliance"; # for alliance
  inputs.c4m-jtag.url = "git+https://git.libre-soc.org/git/c4m-jtag.git";
  inputs.c4m-jtag.flake = false;

  outputs = { self, nixpkgs, c4m-jtag }:
    let
      supportedSystems = [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];

      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; overlays = [ self.overlay ]; });
    in
    {
      overlay = final: prev: {
        python3Packages = prev.python3Packages.override {
          overrides = pfinal: pprev: {
            libresoc-ieee754fpu = pfinal.callPackage ./nix/ieee754fpu.nix {};
            libresoc-openpower-isa = pfinal.callPackage ./nix/openpower-isa.nix {};
            c4m-jtag = pfinal.callPackage (import ./nix/c4m-jtag.nix { src = c4m-jtag; version = c4m-jtag.lastModifiedDate; }) {};
            bigfloat = pfinal.callPackage ./nix/bigfloat.nix {};
            modgrammar = pfinal.callPackage ./nix/modgrammar.nix {};
            libresoc-nmutil = pfinal.callPackage ./nix/nmutil.nix {};
          };
        };

        libresoc-verilog = final.callPackage (import ./nix/verilog.nix { version = self.lastModifiedDate; }) {};
      };

      packages = forAllSystems (system: {
        verilog = nixpkgsFor.${system}.libresoc-verilog;
      });

      defaultPackage = forAllSystems (system: self.packages.${system}.verilog);
    };
}
