# The license for this file is included in the `nix` directory next to this file.

{
  description = "FOSS CPU/GPU/VPU/SoC all in one, see https://libre-soc.org/";

  inputs.nixpkgs.url = "github:L-as/nixpkgs?ref=alliance"; # for alliance
  inputs.c4m-jtag.url = "git+https://git.libre-soc.org/git/c4m-jtag.git";
  inputs.c4m-jtag.flake = false;
  inputs.nmigen.url = "git+https://git.libre-soc.org/git/nmigen.git";
  inputs.nmigen.flake = false;
  inputs.nmigen-soc.url = "git+https://git.libre-soc.org/git/nmigen-soc.git";
  inputs.nmigen-soc.flake = false;

  outputs = { self, nixpkgs, c4m-jtag, nmigen, nmigen-soc }:
    let
      getv = x: builtins.substring 0 8 x.lastModifiedDate;

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
            c4m-jtag = pfinal.callPackage (import ./nix/c4m-jtag.nix { src = c4m-jtag; version = getv c4m-jtag; }) {};
            bigfloat = pfinal.callPackage ./nix/bigfloat.nix {};
            modgrammar = pfinal.callPackage ./nix/modgrammar.nix {};
            libresoc-nmutil = pfinal.callPackage ./nix/nmutil.nix {};

            nmigen-soc = pprev.nmigen-soc.overrideAttrs (_: {
              doCheck = false;
              src = nmigen-soc;
              setuptoolsCheckPhase = "true";
            });

            nmigen = pprev.nmigen.overrideAttrs (_: {
              src = nmigen;
            });
          };
        };

        libresoc-verilog = final.callPackage (import ./nix/verilog.nix { version = getv self; }) {};
        libresoc-ilang = final.callPackage (import ./nix/ilang.nix { version = getv self; }) {};
      };

      packages = forAllSystems (system: {
        verilog = nixpkgsFor.${system}.libresoc-verilog;
        ilang = nixpkgsFor.${system}.libresoc-ilang;
        openpower-isa = nixpkgsFor.${system}.python3Packages.libresoc-openpower-isa;
      });

      defaultPackage = forAllSystems (system: self.packages.${system}.verilog);
    };
}
