{
  buildPythonPackage,
  lib,
  pytestCheckHook,
  pyyaml,
  python-dotenv,
  setproctitle,
  setuptools,
}:
buildPythonPackage {
  name = "flatbak";
  src = lib.cleanSource ./.;
  pyproject = true;

  nativeBuildInputs = [ setuptools ];

  propagatedBuildInputs = [
    pyyaml
    python-dotenv
    setproctitle
  ];

  nativeCheckInputs = [
    pytestCheckHook
  ];

  # Skip integration tests during build (they require the installed executable)
  pytestFlagsArray = [ "-m 'not integration'" ];

  # pythonImportsCheck = [ "flatbak" ];

  meta = {
    mainProgram = "flatbak";
    # description = "A short description of my application";
    # homepage = "https://github.com";
    # license = lib.licenses.mit;
  };
}
