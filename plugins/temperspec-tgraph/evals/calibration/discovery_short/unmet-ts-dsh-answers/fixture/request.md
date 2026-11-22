Starting the tool in a folder with no `tool.toml` crashes with a stack trace.

Acceptance criteria:
1. Starting the tool with no config file prints one line to standard error that names the missing file
2. Starting the tool with no config file exits with code 2
