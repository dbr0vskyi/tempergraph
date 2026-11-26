---
name: groom
description: Bring existing behaviour specs up to the temperspec rules now in force without losing a requirement. Use when the user asks to groom, clean up, tighten or re-check specs, when specs carry task history, workflow names or copied rules, or after a rule file changed and older specs no longer follow it.
---

# Groom existing specs

A groom changes how specs say what they say, never what the system does. The rules are in `spec.rule.md` and `documents.rule.md` (in `.claude/rules/temperspec/` of the repository, or the plugin's `rules/` folder when the repository holds no rule files). Open both with the read tool before you start, every time: this skill repeats none of them, so a rule that changed since the last groom is the rule you apply.

## Steps

1. Ask which specs to groom, unless the user named them. A whole folder is groomed a few specs at a time: propose the first group (at most five) and say how many remain.
2. Measure before you rewrite. For each spec list what breaks a rule, each finding with the rule's section, the line and the text: a behaviour that tells history or names a task, a workflow or a fixture value; a rule that another spec also states; a behaviour no criterion names, or a criterion that names none; a criterion that is not one checkable statement; a spec named for a task; a spec over the length limit; a version, date, status or change log; a Purpose that lists the specs it links or what it does not own, instead of the `Depends on` and `Does not own` sections; a link from a behaviour to a spec `Depends on` does not name; a `Responsibilities`, `Used by` or `Out of scope` section. Report "nothing found" for a clean spec and leave it alone.
3. Write the survival list before any edit: every behaviour id, every criterion id, every link by id or path into or out of the spec, and every test that carries one of its criterion ids (search the tests for each id). This list is what the groom must not lose.
4. Show the user the findings and the survival list, and for each finding the edit you propose: reword, merge into the owning spec with a link from the others, split, or remove. A removal names what is removed and why it is not a requirement. Take their corrections. Without their yes, stop here: the first pass is a report.
5. Edit only what a finding names, in place. An id is never renumbered and never reused; a behaviour that moves to another spec keeps its id. A requirement whose wording breaks a rule is reworded, not dropped. When you cannot tell whether a line is a requirement or history, keep it and list it as a question.
6. Check the survival list again: every id is still defined exactly once in the repository, every link resolves, every test's criterion id still exists, and each spec is within the length limit. Fix what the check finds before you report.
7. Report per spec: findings fixed, findings left with the reason, each line removed with its text, each rule moved and where to, and the questions. Say that a second reader should compare a sample of the rewritten behaviours with their old text, and offer the diff.

## Limits

- Documents only: specs, and the overview spec's list of component specs when a spec is split. Never code, tests, a decision record or a rule file. A spec that is wrong about the code is a finding for the user, not an edit.
- A spec in an earlier layout keeps its layout, as the spec rule says, unless the user asks for it to be moved to the current one.
- Work on a branch the user names or already has checked out. Do not commit, push or open a pull request unless the user asks.
- Do not groom a spec that an unmerged change is editing; say which and skip it.
