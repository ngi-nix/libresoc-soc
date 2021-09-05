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
      overlay = final: prev: {};
    };
}
