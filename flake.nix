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
  inputs.nix-litex.url = "git+https://git.sr.ht/~lschuermann/nix-litex?ref=main";
  inputs.nix-litex.flake = false;

  outputs = { self, nixpkgs, c4m-jtag, nmigen, nmigen-soc, nix-litex }:
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
        python3Packages = prev.python3Packages.override {
          overrides = lib.composeExtensions (litex final).pythonOverlay (pfinal: pprev: {
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
          });
        };

        libresoc-pre-litex = final.callPackage (import ./nix/pre-litex.nix { version = getv self; }) {};
        libresoc-ls180 = final.callPackage (import ./nix/ls180.nix { version = getv self; }) {};
        libresoc-pinmux = final.callPackage (import ./nix/pinmux.nix { version = getv self; }) {};
      };

      packages = forAllSystems (system: {
        soc = nixpkgsFor.${system}.python3Packages.libresoc-soc;
        pre-litex = nixpkgsFor.${system}.libresoc-pre-litex;
        pinmux = nixpkgsFor.${system}.libresoc-pinmux;
        ls180 = nixpkgsFor.${system}.libresoc-ls180;
        openpower-isa = nixpkgsFor.${system}.python3Packages.libresoc-openpower-isa;
        debugNixpkgs = nixpkgsFor.${system};
      });

      defaultPackage = forAllSystems (system: self.packages.${system}.pre-litex);
    };
}
