"""The release-notes workflow: one judged step and the outcome gate (the engine's minimal package, PKG §2.7).

The step may run `git describe` and `git log` only; the checks run the same two commands and hand the
change list to the judges, which read files only (live check L-25, 2026-11-21)."""

from tempergraph.api import Gate, Judge, Routing, Step, Workflow, text

from .checks import draft_check


def workflow():
    return Workflow(
        order=["draft"],
        routing=Routing(description="Write release notes for the changes since the last tag"),
        issue_repository="acme/release-notes",
        allow_commands=["git describe", "git log"],
        units={
            "draft": Step(
                prompt=text("prompts/draft.md"), tools=["read", "write", "shell"], commands=["git describe", "git log"],
                produces={"notes": "file"},
                summary="Write the release notes", timeout_s=900,
                model="medium", effort_ladder=["medium", "high"],
                sizing="It writes one short document from a list of changes it reads; a repeated blocker from a "
                       "trusted judge earns one retry at high effort",
                gate=Gate(check=draft_check, judge=Judge(
                    file="judges/draft.md", references=["notes"], model="medium", effort="medium",
                    sizing="It reads one file against a few criteria")),
            ),
        },
    )
