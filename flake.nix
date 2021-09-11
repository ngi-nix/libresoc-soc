# The license for this file is included in the `nix` directory next to this file.

{
  description = "FOSS CPU/GPU/VPU/SoC all in one, see https://libre-soc.org/";

  inputs.nixpkgs.url = "github:L-as/nixpkgs?ref=alliance"; # for alliance

  outputs = { self, nixpkgs }:
    let
      version = builtins.substring 0 8 self.lastModifiedDate;

      supportedSystems = [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];

      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; overlays = [ self.overlay ]; });
    in
    {
      overlay = self: super: {
        python3Packages = super.python3Packages.override {
          overrides = pself: psuper: {
            libresoc-ieee754fpu = pself.callPackage ./nix/ieee754fpu.nix {};
            libresoc-openpower-isa = pself.callPackage ./nix/openpower-isa.nix {};
            bigfloat = pself.callPackage ./nix/bigfloat.nix {};
            libresoc-nmutil = pself.callPackage ./nix/nmutil.nix {};
          };
        };

        libresoc-verilog = self.callPackage (import ./nix/verilog.nix { inherit version; }) {};
      };

      packages = forAllSystems (system: {
        verilog = nixpkgsFor.${system}.libresoc-verilog;
      });

      defaultPackage = forAllSystems (system: self.packages.${system}.verilog);
    };
}
