# Which sources a run's request can come from, and what flows back to them

## Problem statement

A run starts from a request typed on the command line: plain text, a tracker key, or the path of a file ([CON-B9](../specs/contracts.spec.md), [ROP-B11](../specs/run-options.spec.md)). The owner asked on 2026-11-26 that temperspec also take a GitHub issue, a Jira story and other kinds of work item, and that the possible sources be analysed first. Issue #102 asked the same for Jira and Azure DevOps, and for the way back to them.

The questions: which sources are possible; how an unattended run (`claude -p` step sessions, no person at the keyboard) gets their content and with what sign-in; how a work item's fields map to what triage writes (criteria, intent, uncertainties); what should be written back to the source; what the fetched text puts at risk; and which part is an engine capability and which part belongs to a workflow package ([ADR `the-engine-names-no-workflow`](../adr/the-engine-names-no-workflow.adr.md)).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Request resolution: `resolve_request`, the input kinds `any`, `text`, `tracker_key`, `file`, `resolver` | code | `engine/src/tempergraph/catalog.py:99` |
| `run` takes the request as positional words | code | `engine/src/tempergraph/cli/main.py:77`, `:475` |
| The judge's prompt gets `inputs["request"]` as its reference | code | `engine/src/tempergraph/run/nodes.py:1722-1734`, `run/judging.py:149` |
| Input and routing declarations | spec | [CON-B9](../specs/contracts.spec.md); [ROP-B10, ROP-B11](../specs/run-options.spec.md) |
| Callables are pure and call no model; validation calls a resolver twice and compares | spec | [workflow package](../specs/workflow-package.spec.md) (callable signatures behaviour) |
| The judge's references hold the request whole up to 32,000 characters | spec | [judge and verdict](../specs/judge-and-verdict.spec.md) |
| Run text never reaches argv or published text; session content read by a model is datamarked and fenced | spec | [SEC-B11 and the publishing behaviours](../specs/security.spec.md) |
| Lifecycle hooks: events, facts file, 60 s limit, never change the run | spec | [HOK-B1 to HOK-B5](../specs/lifecycle-hooks.spec.md) |
| Tracker integrations are separate plugins that read `facts` and register hooks | spec | [SHL-B16](../specs/plugin-shell.spec.md) |
| A judge reads a remote tracker through the MCP view proxy, else grades UNVERIFIABLE | spec, issue | [executor interface](../specs/executor-interface.spec.md); #46 (L-33 rest) |
| Step and judge sessions get no MCP server they do not declare | issue | #21 (merged on the batch branch), #165 |
| temperspec declares `input.kind: text`; triage's prompt renders `{request}` and says "If it names a file, read that file: it is the task" | code | `plugins/temperspec-tgraph/blueprint.json:423`, `prompts/triage.md:10` and step 1 |
| temperspec's triage criteria `ts-tri-criteria` (every criterion is stated by the task) and its blocked rule (no criterion, no run) | spec | `plugins/temperspec-tgraph/docs/specs/triage.spec.md` |
| The pull request description is written by the last stage with no model | spec | `plugins/temperspec-tgraph/docs/specs/pull-request-description.spec.md` |
| Contributors pass "the issue's text as the run request, not its URL or a file outside the repository" | docs | `CONTRIBUTING.md` section 4 |
| The issue form's sections (Summary, Why, Done when, Specs and sources, Area, priority, effort, Depends on) | docs | `.github/ISSUE_TEMPLATE/feature.yml`, `bug.yml` |
| The owner's batch queue: one request file per run, written by an agent from an issue and its reviews | branch | `dbr0vskyi/batch-queue`: `batch-queue/QUEUE.md`, `batch-queue/tasks/i170c.md`, `tasks/i21b.issue.md`, `observations.md` |
| A missing request file passes `run --check` | issue | #175 |
| The run trailer and the run line in temperspec's pull request | issue | #94, #103 |
| GitHub CLI `gh issue view --json`, `gh pr view --json reviews,comments`, the REST `author_association` field | public docs | cli.github.com/manual, docs.github.com/rest |
| Jira Cloud REST API v3 (description in Atlassian Document Format), API tokens, remote issue links; Jira's GitHub integration links branches, commits and pull requests that name the issue key | public docs | developer.atlassian.com/cloud/jira/platform/rest/v3, support.atlassian.com |
| GitLab `glab issue view`, Azure DevOps `az boards work-item show`, Linear's GraphQL API and its MCP server, Confluence REST API v2 | public docs | docs.gitlab.com, learn.microsoft.com/azure/devops, linear.app/developers, developer.atlassian.com/cloud/confluence |

## Key findings

### F1 The engine resolves a request with no fetch, and a workflow's resolver may not fetch either `confirmed`

`resolve_request` (`catalog.py:99`) joins the positional words into one text. `text` and `any` hash it into `t-<hash>`, `tracker_key` checks the shape `ABC-123` and takes it as the task id, and `file` checks that the path exists and gives `f-<stem>-<hash>`. Nothing is read from a tracker, and a `file` request stays a path: the file's content is not copied into the run. A workflow may declare its own `resolver`, but the package spec requires every callable but a script and a finalizer to be pure over its input and the files it may read, and validation calls a resolver on the declared examples twice and compares the answers. A resolver that calls `gh` or a REST API breaks that rule: the answer depends on the network and on the item's current text. So no source outside the repository can enter a run through today's contract without a new engine capability.

### F2 temperspec takes text, and a file only by the triage session's own reading `confirmed`

temperspec declares `input.kind: text`. Its triage prompt renders the request in place and tells the session that a request naming a file is that file. The batch queue starts every run that way: `tempergraph run temperspec … batch-queue/tasks/<id>.md`, so the request text is a path of about 26 characters. Two consequences follow from the code:

- The judge's reference is `inputs["request"]` (`run/nodes.py:1727`), the path and not the task. A judge that checks `ts-tri-criteria` ("every acceptance criterion in the triage note is stated by the task") sees the task only if its read view opens the file.
- The file is read in the worktree. When it is missing at the worktree's base ref, the first step blocks after spend (#175, run i144b).

### F3 The batch queue shows what a work-item request really holds `confirmed`

The queue's request files (`batch-queue/tasks/*.md`) are written by an agent from an issue, never pasted. `i170c.md` holds the issue's criteria, the merges the run builds on, the findings of an earlier review, what earlier runs already did and what they leave out, and the follow-ups to file. `i21b.issue.md` is an issue's body in the form's sections. So a request from a work item is the item plus an operator's addendum. A source capability that takes only the item would drop the addendum, and an operator who must merge them by hand gains little.

### F4 The repository's issue form already holds the fields triage writes `confirmed`

The feature form's sections map one to one onto the triage note ([triage](../../../temperspec-tgraph/docs/specs/triage.spec.md), `task-notes.rule.md`):

| Issue section | Triage note |
|---|---|
| Summary, Why | `Intent`: goal |
| Done when (a checklist) | Acceptance criteria, copied word for word |
| Specs and sources | Existing documents; starting points for reading sessions |
| Area label | Which package's docs the run writes to |
| Effort label (XS to XL) | A hint for the lane and complexity, never a decision |
| Depends on | Assumption rows or `owner` uncertainty rows |
| An owner `question` comment with `Until answered: …` | An owner decision with its default ([conversation](../../../temperspec-tgraph/docs/specs/conversation.spec.md)) |
| Later owner comments | Clarifications that may close an uncertainty before discovery |
| A `bug` form's What happened, What the spec says, How to reproduce, Evidence | Intent and the uncertainty categories `behaviour` and `evidence` |

A Jira story maps the same way with two differences: acceptance criteria are often a custom field whose id differs per site (`customfield_<n>`), or a heading inside the description; and the description is Atlassian Document Format JSON, which needs a model-free conversion to Markdown. Story points map to the effort hint, issue links (`blocks`, `is blocked by`) to Depends on, the epic or parent to context.

### F5 Who can write the item decides how far its text can be trusted `supported`

The repository is going public (Apache-2.0). Anyone with a GitHub account can open an issue on a public repository and edit their own issue and comments later. A request taken from such an issue reaches step sessions that write files and run commands. Three facts make that a real risk:

- The step prompt renders `{request}` as given, and the judge's prompt puts it under `### request` with no fence (`run/judging.py:149`). Only session content read by the reviewer is datamarked today (SEC-B11).
- Markdown holds text a person never sees in the browser: HTML comments (`<!-- … -->`), collapsed `<details>` blocks, zero-width and tag characters. This repository's own agent protocol uses hidden comment markers.
- An item can change between `run --check`, the run's start and a resume, so the text the operator checked may not be the text the run reads.

GitHub's REST API gives each issue and comment an `author_association` (`OWNER`, `MEMBER`, `COLLABORATOR`, `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, `NONE`). Jira and the other trackers limit who can create an item to project members, so their risk is an insider's, not a stranger's.

### F6 The sign-in of an unattended run is the operator's, and the engine process is where it lives `inferred`

Since #21 a step session runs with `--strict-mcp-config` and no claude.ai connector, so a session cannot reach the account's Jira, Linear or Confluence connectors unless the step declares the server and the operator's configuration defines it. A claude.ai connector also needs an interactive OAuth grant and belongs to the claude.ai account, not to the machine. The engine process, by contrast, already runs `gh` with the operator's sign-in (filing, proposals, the last stage) and already reads named credentials from `<home>/config/credentials/<profile>` without putting values in argv or logs (security spec). A model-free fetch in the engine at the run's start therefore needs no new sign-in model: `gh` for GitHub, a token named in the credentials file for the others. On the owner's Raspberry Pi, `gh` is signed in, and a shim refuses `pr create` and every write through `gh api` (`batch-queue/QUEUE.md`, "Launching on this machine"), so a read-only fetch works there today and a write-back would be refused until the shim allows it.

### F7 The way back exists only for GitHub, and only through the workflow's own last stage `confirmed`

temperspec's last stage pushes the branch and opens a draft pull request with a model-free description; it writes no `Closes #n`, and no line ties the pull request to the item or the run (#103 asks for the run line, #94 for the trailer). The engine's lifecycle hooks run a detached program on `started`, `paused`, `finished` and `failed` with a facts file (HOK-B3), and SHL-B16 leaves tracker integrations (states, rollout) to a separate plugin built on those hooks. The facts file has no field for where the request came from, so a hook today cannot tell which item to comment on. Jira's GitHub integration links a branch, a commit and a pull request to an issue when their name or title holds the issue key, which is a way back that writes nothing to Jira.

### F8 Each source, assessed `inferred`

| Source | Possible | Fetch in an unattended run | Sign-in | Maps to triage | Way back | Main risk |
|---|---|---|---|---|---|---|
| Typed text (today) | yes | none | none | as written | none | none new |
| A file in the repository (today) | yes | read in the worktree | none | as written | none | missing at the base ref (#175) |
| A file outside the repository, or standard input (a pasted export, an e-mail, a review) | yes | the engine copies it at start | none | as written | none | none new; the operator chose the text |
| GitHub issue | yes | `gh issue view <n> --json title,body,labels,state,author,comments,url` | `gh` sign-in | the form's sections (F4) | `Closes #n` in the pull request; a `result` comment; the assignment rule's claim | text by strangers on a public repository (F5) |
| GitHub pull request review or review comments | yes | `gh pr view <n> --json reviews,comments,headRefName`, review threads through `gh api` | `gh` sign-in | no criteria: one per blocking finding ("finding n is resolved") | a reply in the thread, a commit link | the same as an issue; the run's base must be the pull request's head |
| Jira story, task or bug | yes | REST v3 `GET /rest/api/3/issue/<key>`, or a CLI such as `jira` or Atlassian's `acli` | API token (Cloud) or personal access token (Data Center), named in the credentials file | F4, with a per-site mapping of the criteria field | the key in branch and pull request title (no write); a comment or remote link; a transition only by a person's choice | per-site field ids; ADF conversion; insider text |
| GitLab issue | yes | `glab issue view <n> --output json`, or REST | `glab` sign-in or token | as a GitHub issue (no issue form by default) | `Closes #n` in a merge request; a note | as GitHub; the code host's merge request is a separate finalizer (#12) |
| Azure DevOps work item | yes | `az boards work-item show --id <n>`, or REST | personal access token | Title, Description (HTML), Acceptance Criteria (a standard field of a user story) | `AB#<n>` in a commit or pull request on GitHub; a discussion comment | HTML conversion |
| Linear issue | yes | GraphQL API (`issue(id:)`); an official MCP server exists but needs OAuth | API key | title, description (Markdown); criteria by convention | the identifier in branch or title links it (Linear's GitHub integration); a comment | none beyond insider text |
| Confluence page or another document (Google Docs, Notion) | in part | REST v2 page body (storage format) or the document's export | API token, or an export | a specification of several tasks: context, not one task; criteria are rarely there | a comment, rarely wanted | size; the page is not one task |
| A web URL | in part | an HTTP fetch of an allowed host | none or unknown | as text after HTML conversion | none | anything on the page; following links; requests to inner hosts |
| A chat thread (Slack, Teams) | only as an export | an export on standard input | none | as text | none | who said what is lost |

## Conclusions

1. Every work-item source in F8 is possible, and none can enter through today's contract: a workflow's resolver may not fetch (F1). What every workflow needs, coding or not, is the same contract, so that part is the engine's and names no workflow and no tracker: a **request source**. A run takes a source reference (for example `gh:#170`, `jira:PROJ-123`, `file:<path>`, `-` for standard input); the source that owns the prefix fetches the item once at the start with no model, read-only; the engine writes a snapshot into the thread folder: `request.md` (the visible text in fixed sections) and a record with source, reference, URL, title, state, author and the author's trust, fetch time and content hash. The task id comes from the reference (`gh-170`, `PROJ-123`), so the same item finds the same thread.
2. The snapshot is the request from then on (F2, F5). Every step reads it, the judge's reference is its text and not a path, `run --check` fetches and shows it before spend (which also answers #175 for a file request), and `resume` uses the frozen copy. A changed item is seen only when the operator asks for a refresh, which records the old and the new hash.
3. The operator's addendum stays (F3): a run takes a source and request text together, the snapshot holding the item and the text in two labelled parts. The batch queue's request files become "the issue plus this note".
4. Fetched text is untrusted input (F5). The snapshot keeps only what a person sees: hidden comments, collapsed blocks and invisible characters are dropped and counted. The step and judge prompts fence it with a per-run boundary and say it is data. A source reports each author's trust in its own terms; comments are kept only from authors whose trust reaches the level the workflow or the operator sets, and an item whose own author is below it is refused at `run --check` unless the operator passes it explicitly. The default for a GitHub source: owner, member and collaborator.
5. The engine ships no tracker or code-host source (the owner, 2026-11-26: building them into the engine would narrow it, since tempergraph is for any workflow and not only coding). The engine keeps the sources that belong to no service: request text, files (copied at start) and standard input. GitHub issues and pull request reviews (through `gh`, F6), Jira, GitLab, Azure DevOps, Linear and Confluence are each a source plugin of the contract, found the way workflow packages are found, with its own sign-in (a CLI's, or a token named in the credentials file); a workflow package may also ship a source of its own. Any workflow can take any installed source, and a workflow may declare which sources it accepts.
6. A run writes nothing back to its source unless its workflow declares it (the owner, 2026-11-26). The engine puts the source in the run's facts (kind, reference, URL), so a finalizer or a declared step knows the item, and offers a model-free way to post through the source plugin; an operator setting or a hook does not add a write the workflow did not declare. A workflow that does write puts only fixed words, links, the run's id and the outcome in it, never request text (security spec). For temperspec that is what its pull request says (`Closes #170` for an issue of the same repository, the key in branch and title for Jira and Linear, which links with no write); a comment on the item would be its own declared choice.
7. A pull request review is a source of a different shape: it has no criteria and it targets an existing branch. It maps to one criterion per blocking finding and a run based on the pull request's head; the engine's rerun with feedback ([RRN](../specs/reruns-and-feedback.spec.md)) stays the way for a run's own pull request.
8. A Confluence page, another document, a web URL and a chat thread are context, not a task (F8): they carry no criteria and often several tasks. They enter as a second, named input snapshotted the same way (`--input context=<reference>`), and a URL only for hosts the operator allows.
9. For temperspec (its own docs first, then the engine change, per the engine's rule): declare which sources it accepts; teach triage to read the snapshot's sections (F4) and to treat comments by their author's trust; make the pull request description name the source and close it when it is an issue of the same repository; put a tracker key in the branch name.
10. Starting a run when an item appears or changes (picking up issues automatically) is out of this note's scope (the owner, 2026-11-26). It would be a separate engine capability, a **watch**, configured like a schedule ([schedules](../specs/schedules.spec.md)): a watch names events of a source (an item labelled, opened or commented) and the workflow to run for each, and starts the run with the item as its request source. It reuses this note's sources and snapshot, and the schedule's rules for an unattended caller, spend caps and overlap.

## Open questions

1. Which trust level may start a run from a GitHub issue once the repository is public? Until answered: owner, member and collaborator; anything lower is refused unless the operator passes the item explicitly on that run.
2. Which Jira field holds acceptance criteria on the sites that will use this? The sources cannot tell; a per-site mapping in the operator's configuration is assumed.
