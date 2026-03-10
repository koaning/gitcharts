{
  pkgs,
  python3,
  ...
}:
pkgs.writeShellApplication {
  name = "git-charts";

  runtimeInputs = let
    pythonWithPkgs = python3.withPackages (p:
      with p; [
        marimo
        polars
        altair
        httpx
        pydantic
        diskcache
      ]);
  in [
    pythonWithPkgs
  ];

  # Invoke the application as normal
  text = ''
    python3 ${./git_archaeology.py} "$@"
  '';
}
