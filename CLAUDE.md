# Project Guidelines (CLAUDE.md)

## Development Principles
- Interpret all requests in the context of professional software engineering.
- Always inspect files before modifying them using `view`, `glob`, or `grep`.
- Prefer surgical editing (`edit`) over complete file rewrites (`write`).
- Use `bash` to run commands, tests, and dependency installations.
- Only perform actions explicitly requested by the user. Do not push to remote repositories or deploy without confirmation.
- Delegate complex subtasks to specialized subagents via the `agent` tool (`researcher`, `coder`, `tester`, `devops`).
