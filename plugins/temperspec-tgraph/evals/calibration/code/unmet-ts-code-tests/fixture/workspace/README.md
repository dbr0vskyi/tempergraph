# tool

A small command line tool. It reads its settings from `tool.toml` in the folder it is started in.

Run the tests with `pytest`.

When `tool.toml` is missing, the tool prints one line that names the file to standard error and exits with code 2.
