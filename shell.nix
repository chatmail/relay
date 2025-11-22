{ pkgs ? import <nixpkgs> {} }:

let
  # Helper to expose libstdc++ / gcc runtime to venv
  gccEnv = pkgs.buildEnv {
    name = "gcc-runtime";
    paths = [
      pkgs.stdenv.cc.cc.lib
      pkgs.libgcc
      pkgs.libunwind
    ];
  };
in

pkgs.mkShell {
  buildInputs = [
    pkgs.python313
    gccEnv
  ];

  shellHook = ''
    # make sure the venv sees shared libraries
    export LD_LIBRARY_PATH="${gccEnv}/lib:$LD_LIBRARY_PATH"

    VENV_DIR=".venv"
    if [ ! -d $VENV_DIR ]; then
      echo "🐍 Creating virtualenv..."
      python3 -m venv $VENV_DIR
    fi

    # Activate venv and prep path
    source $VENV_DIR/bin/activate
    export PATH="$VENV_DIR/bin:$PATH"

    # Upgrade pip and install packages only if missing
    pip install --upgrade pip
    for pkg in sphinx furo sphinx-autobuild sphinxcontrib-mermaid pyinfra gevent greenlet; do
      pip show $pkg >/dev/null 2>&1 || pip install $pkg
    done
  '';
}
