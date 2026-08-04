{pkgs}: {
  deps = [
    pkgs.ghc
    pkgs.openssl
    pkgs.gcc
    pkgs.ninja
    pkgs.cmake
    pkgs.rustup
  ];
}
