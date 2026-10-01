# Execution Rule for Sudo and Long-Running Commands

- Whenever a command requires `sudo` (root privileges) or is expected to be long-running / time-consuming (such as running Mininet benchmarks, heavy network traffic generation, or large test suites):
  - Do NOT execute the command directly via terminal execution tools.
  - Instead, provide the exact step-by-step instructions and shell commands so the user can execute them directly in their terminal.
