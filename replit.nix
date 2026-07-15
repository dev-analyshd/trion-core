{pkgs}: {
  deps = [
    pkgs.openssl
    pkgs.gcc
    pkgs.ninja
    pkgs.cmake
    pkgs.rustup
  ];
}
