# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue, pull request or discussion.

Use GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability** ([direct link](https://github.com/dbr0vskyi/tempergraph/security/advisories/new)). Include what you found, the engine version (`tempergraph --version`), the Claude Code version (`claude --version`), and the smallest steps that show it. Scrub prompts, outputs, tokens and paths from any run record or session log you attach.

You can expect a first answer within a week. Once a fix is ready, the advisory is published with credit to you, unless you ask not to be named.

## Supported versions

tempergraph is pre-release. Only the latest commit on `main` gets security fixes; there are no maintained release branches yet.

## What counts

Reports are most useful where tempergraph promises a boundary and does not keep it, for example:

- a step or judge session that reaches tools, files, directories or environment variables it did not declare;
- a judge that can see a step's reasoning or edit its work;
- a secret that survives into the run log, a detail document, a sink row, carried run state or a filed issue;
- a schedule, hook or launcher that runs a command it was not given.

The engine's intended behaviour is in the [security spec](plugins/tempergraph/docs/specs/security.spec.md) and the [independence guard spec](plugins/tempergraph/docs/specs/independence-guard.spec.md).

Out of scope: problems in Claude Code, LangGraph or other dependencies themselves (report those upstream), and spend that stays inside a run's configured cost cap.
