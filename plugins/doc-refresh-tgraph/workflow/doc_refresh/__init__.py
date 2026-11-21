"""The doc-refresh workflow (the engine's three-step document example, first-release plan T11.1).

`outline` is a script unit with no session; `draft` rewrites the sections the request names and gives a
`size` value that routes a minor rewrite straight to the finalizer; `review` is judged, needs a person's
approval, and can send the run back to `draft`. The finalizer reports where the document was written.
"""

from tempergraph.api import Gate, Judge, Routing, Script, Step, Value, Workflow, text

from .checks import draft_check, outline_check
from .routing import finalize, route_draft, script_outline


def workflow():
    return Workflow(
        order=["outline", "draft", "review"],
        routing=Routing(description="Refresh named sections of a document so they match the repository",
                        when_to_use="A document's named sections are out of date; give its path and the sections"),
        issue_repository="acme/docs",
        units={
            "outline": Script(call=script_outline, produces={"outline": "file"}, side_effects="workspace",
                              summary="List the document's headings", gate=Gate(check=outline_check)),
            "draft": Step(
                prompt=text("prompts/draft.md"), summary="Rewrite the requested sections", timeout_s=900,
                tools=["read", "write"], produces={"doc": "file", "size": Value(choices=["major", "minor"])},
                route=route_draft, route_targets=["review", "finalizer"],
                model="medium", effort="medium", sizing="It rewrites named sections from the repository's files",
                gate=Gate(check=draft_check, judge=Judge(
                    file="judges/draft.md", references=["doc", "outline"], model="medium", effort="medium",
                    sizing="It compares the rewritten sections with the outline and the request"))),
            "review": Step(
                prompt=text("prompts/review.md"), summary="Review the rewrite against the request", timeout_s=600,
                tools=["read"], produces={"verdict": Value(choices=["approve", "redo"])},
                model="medium", effort="medium",
                sizing="It reads one document against the request and gives a verdict",
                gate=Gate(judge=Judge(file="judges/review.md", references=["doc"], model="medium", effort="low",
                                      sizing="It confirms a one-word verdict that a person then approves"),
                          approval=True,
                          back_targets=["draft"])),
        },
        finalizer=finalize,
        finalizer_outcomes=["written"],
    )
