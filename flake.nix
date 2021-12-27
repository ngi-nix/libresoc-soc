# The license for this file is included in the `nix` directory next to this file.

{
  description = "FOSS CPU/GPU/VPU/SoC all in one, see https://libre-soc.org/";

  inputs.nixpkgs.url = "github:L-as/nixpkgs?ref=libresoc"; # for alliance and migen
  inputs.c4m-jtag.url = "git+https://git.libre-soc.org/git/c4m-jtag.git";
  inputs.c4m-jtag.flake = false;
  inputs.nmigen.url = "git+https://git.libre-soc.org/git/nmigen.git";
  inputs.nmigen.flake = false;
  inputs.nmigen-soc.url = "git+https://git.libre-soc.org/git/nmigen-soc.git";
  inputs.nmigen-soc.flake = false;
  inputs.migen.url = "github:m-labs/migen";
  inputs.migen.flake = false;
  inputs.yosys.url = "github:YosysHQ/yosys?rev=a58571d0fe8971cb7d3a619a31b2c21be6d75bac";
  inputs.yosys.flake = false;
  # submodules needed
  inputs.nix-litex.url = "git+https://git.sr.ht/~lschuermann/nix-litex?ref=main";
  inputs.nix-litex.flake = false;

  outputs = { self, nixpkgs, c4m-jtag, nmigen, nmigen-soc, nix-litex, migen, yosys }:
    let
      getv = x: builtins.substring 0 8 x.lastModifiedDate;

      supportedSystems = [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];

      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      litex = pkgs: import "${nix-litex}/pkgs" {
        inherit pkgs;
        pkgMetas = builtins.fromTOML (builtins.readFile ./nix/litex.toml);
        skipChecks = true; # FIXME: remove once checks work
      };

      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; overlays = [ self.overlay ]; });

      lib = nixpkgs.lib;
    in
    {
      overlay = final: prev: {
        python37 = prev.python37.override {
          packageOverrides = lib.composeExtensions (litex final).pythonOverlay (pfinal: pprev: {
            libresoc-ieee754fpu = pfinal.callPackage ./nix/ieee754fpu.nix {};
            libresoc-openpower-isa = pfinal.callPackage ./nix/openpower-isa.nix {};
            c4m-jtag = pfinal.callPackage (import ./nix/c4m-jtag.nix { src = c4m-jtag; version = getv c4m-jtag; }) {};
            bigfloat = pfinal.callPackage ./nix/bigfloat.nix {};
            modgrammar = pfinal.callPackage ./nix/modgrammar.nix {};
            libresoc-nmutil = pfinal.callPackage ./nix/nmutil.nix {};
            libresoc-soc = pfinal.callPackage (import ./nix/soc.nix { version = getv self; }) {};

            nmigen-soc = pprev.nmigen-soc.overrideAttrs (_: {
              doCheck = false;
              src = nmigen-soc;
              setuptoolsCheckPhase = "true";
            });

            nmigen = pprev.nmigen.overrideAttrs (_: {
              src = nmigen;
            });

            migen = pprev.migen.overrideAttrs (_: {
              src = migen;
            });
          });
        };

        yosys = prev.yosys.overrideAttrs (_: {
          version = "0.9+4052";
          src = yosys;
        });

        libresoc-verilog = final.callPackage (import ./nix/verilog.nix { version = getv self; }) { python3Packages = final.python37Packages; };
        libresoc-ls180 = final.callPackage (import ./nix/ls180.nix { version = getv self; }) { python3Packages = final.python37Packages; };
        libresoc-ecp5 = final.callPackage (import ./nix/ecp5.nix { version = getv self; }) { python3Packages = final.python37Packages; };
        libresoc-ecp5-program = final.callPackage (import ./nix/ecp5-program.nix { version = getv self; }) { python3Packages = final.python37Packages; };
        libresoc-pinmux = final.callPackage (import ./nix/pinmux.nix { version = getv self; }) {};
      };

      apps = forAllSystems (system: {
        ecp5 = {
          type = "app";
          program = "${nixpkgsFor.${system}.libresoc-ecp5-program}";
        };
      });
      defaultApp = forAllSystems (system: self.apps.${system}.ecp5);

      packages = forAllSystems (system: {
        soc = nixpkgsFor.${system}.python37Packages.libresoc-soc;
        verilog = nixpkgsFor.${system}.libresoc-verilog;
        pinmux = nixpkgsFor.${system}.libresoc-pinmux;
        ls180 = nixpkgsFor.${system}.libresoc-ls180;
        ecp5 = nixpkgsFor.${system}.libresoc-ecp5;
        ecp5-program = nixpkgsFor.${system}.libresoc-ecp5-program;
        openpower-isa = nixpkgsFor.${system}.python37Packages.libresoc-openpower-isa;
        debugNixpkgs = nixpkgsFor.${system};
      });

      defaultPackage = forAllSystems (system: self.packages.${system}.verilog);
    };
}
