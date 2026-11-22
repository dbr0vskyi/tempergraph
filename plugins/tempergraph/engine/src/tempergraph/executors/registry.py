"""The executor registry and judge executor selection (EXI-B16, EXI-B17, EXI-B24).

Names are constants registered in a fixed order; workflow data selects one by name and never supplies a
path or a command. Release 1 registers ``claude`` only (ADR-0091). Tests build their own `Registry`
holding stand-ins.
"""

from __future__ import annotations

from tempergraph.constants import EXECUTOR_NAMES
from tempergraph.contracts import Executor


class UnknownExecutor(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"unknown executor {name!r}")
        self.name = name


class NoJudgeExecutor(LookupError):
    pass


class Registry:
    def __init__(self) -> None:
        self._items: dict[str, Executor] = {}

    def register(self, executor: Executor) -> None:
        if executor.name not in EXECUTOR_NAMES:
            raise ValueError(f"executor name {executor.name!r} is not a registered constant")
        self._items[executor.name] = executor

    def get(self, name: str) -> Executor:
        if name not in self._items:
            raise UnknownExecutor(name)
        return self._items[name]

    def available(self) -> list[str]:
        """Registered names in the constant registration order."""
        return [n for n in EXECUTOR_NAMES if n in self._items]

    def judge_executor(self, step_executor: str, gate_judge_executor: str | None,
                       operator_override: str | None, designated: str | None = None) -> str:
        """EXI-B24 order: override, the gate's, the step's if it restricts judge tools, the designated,
        else the first registered executor that declares it."""
        for name in (operator_override, gate_judge_executor):
            if name:
                self.get(name)
                return name
        if step_executor in self._items and _can_judge(self._items[step_executor]):
            return step_executor
        if designated and designated in self._items and _can_judge(self._items[designated]):
            return designated
        for name in self.available():
            if _can_judge(self._items[name]):
                return name
        raise NoJudgeExecutor(f"no registered executor can hold a judge to read-only tools (step on {step_executor})")


def _can_judge(ex: Executor) -> bool:
    caps = ex.capabilities()
    return caps.restricts_judge_tools and caps.prompt_off_argv


def default_registry() -> Registry:
    """The shipped registry: `claude` only in release 1 (ADR-0091)."""
    from tempergraph.executors.claude import ClaudeExecutor

    reg = Registry()
    reg.register(ClaudeExecutor())
    return reg
