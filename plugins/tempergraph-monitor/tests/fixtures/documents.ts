// Written by make_fixtures.py; do not edit. The same documents as the .json files beside it.

export const status = {
  "schema_version": 1,
  "generated_at": "2026-11-20T10:40:23.274Z",
  "threads": [
    {
      "thread_id": "demo/T-1",
      "workflow": "demo",
      "state": "paused",
      "alive": false,
      "pending_gates": [
        {
          "unit": "review",
          "item": null,
          "kind": "escalation",
          "resume": "tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
        }
      ],
      "log_path": "/work/repo/.tempergraph/runs/demo/T-1/run.jsonl",
      "cost": {
        "reported": 0.1,
        "incomplete": false,
        "completeness": "complete",
        "counters": {
          "reported": 0.09999999999999999,
          "estimated": 0.0,
          "estimated_only": 0.0,
          "sessions": 10,
          "reported_sessions": 10,
          "estimated_sessions": 0,
          "unmeasured": 0
        }
      },
      "executors": {
        "claude": "standin"
      },
      "settings_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "overridden_keys": [],
      "settings_stale": false,
      "workspace": {
        "mode": "worktree",
        "path": "/work/repo.worktrees/demo--T-1",
        "branch": "tg/demo/T-1",
        "state": "active"
      },
      "exit_code": 3,
      "exit_reason": "escalation"
    }
  ]
} as const

export const detailPaused = {
  "schema_version": 1,
  "generated_at": "2026-11-20T10:40:23.286Z",
  "run": {
    "thread_id": "demo/T-1",
    "workflow": "demo",
    "state": "paused",
    "alive": false,
    "pending_gates": [
      {
        "unit": "review",
        "item": null,
        "kind": "escalation",
        "resume": "tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
      }
    ],
    "log_path": "/work/repo/.tempergraph/runs/demo/T-1/run.jsonl",
    "cost": {
      "reported": 0.1,
      "incomplete": false,
      "completeness": "complete",
      "counters": {
        "reported": 0.09999999999999999,
        "estimated": 0.0,
        "estimated_only": 0.0,
        "sessions": 10,
        "reported_sessions": 10,
        "estimated_sessions": 0,
        "unmeasured": 0
      }
    },
    "executors": {
      "claude": "standin"
    },
    "settings_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    "overridden_keys": [],
    "settings_stale": false,
    "workspace": {
      "mode": "worktree",
      "path": "/work/repo.worktrees/demo--T-1",
      "branch": "tg/demo/T-1",
      "state": "active"
    },
    "exit_code": 3,
    "exit_reason": "escalation",
    "segment": 0,
    "last_seq": 55,
    "run_dir": "/work/repo/.tempergraph/runs/demo/T-1",
    "plan_digest": "a577bffc8fe5d4dfcfca250fce4ceb2f8220963cb011a2c806d79ac62c64176b"
  },
  "plan": [
    {
      "name": "draft",
      "kind": "step",
      "gated": true,
      "executor": "claude",
      "judge_executor": "claude",
      "alias": null,
      "edges": [
        {
          "target": "review",
          "on": "PROCEED"
        },
        {
          "target": "human",
          "on": "ESCALATE"
        },
        {
          "target": "end",
          "on": "STOP"
        }
      ],
      "items": null
    },
    {
      "name": "review",
      "kind": "step",
      "gated": true,
      "executor": "claude",
      "judge_executor": "claude",
      "alias": null,
      "edges": [
        {
          "target": "finalizer",
          "on": "PROCEED"
        },
        {
          "target": "draft",
          "on": "BACK"
        },
        {
          "target": "human",
          "on": "ESCALATE"
        },
        {
          "target": "end",
          "on": "STOP"
        }
      ],
      "items": null
    },
    {
      "name": "finalizer",
      "kind": "finalizer",
      "gated": false,
      "executor": null,
      "judge_executor": null,
      "alias": null,
      "edges": [],
      "items": null
    }
  ],
  "plan_stale": false,
  "units": [
    {
      "name": "draft",
      "state": "passed",
      "visits": [
        {
          "visit": 1,
          "entered_from": "start",
          "attempts": [
            {
              "attempt": 1,
              "item": null,
              "started_at": "2026-11-20T10:40:22.773Z",
              "ended_at": "2026-11-20T10:40:22.919Z",
              "step": {
                "sessions": [
                  {
                    "session_key": "draft.1.step",
                    "kind": "step",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "s-draft",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.1.step/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 0,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:22.773Z",
                    "ended_at": "2026-11-20T10:40:22.775Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.1.step/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.1.step/live.json"
                  }
                ]
              },
              "check": {
                "result": "PASS",
                "environmental": false,
                "duration_s": null,
                "output_path": null,
                "evidence": "ok"
              },
              "judge": {
                "sessions": [
                  {
                    "session_key": "draft.1.judge",
                    "kind": "judge",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "j",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.1.judge/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 1,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:22.910Z",
                    "ended_at": "2026-11-20T10:40:22.912Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.1.judge/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.1.judge/live.json"
                  }
                ],
                "criteria": [
                  {
                    "n": 1,
                    "id": "c-file",
                    "status": "UNMET"
                  }
                ],
                "met": 0,
                "total": 1,
                "gap": false,
                "blockers": [
                  {
                    "id": "c-file",
                    "evidence": null,
                    "fix": null
                  }
                ],
                "confidence": 0.8,
                "confidence_source": "judge",
                "guard": "clean"
              },
              "gate": {
                "verdict": "RETRY",
                "route_target": "draft",
                "token": "RETRY",
                "guard": "clean"
              },
              "repeat_cause": "blocker:c-file"
            },
            {
              "attempt": 2,
              "item": null,
              "started_at": "2026-11-20T10:40:22.926Z",
              "ended_at": "2026-11-20T10:40:23.043Z",
              "step": {
                "sessions": [
                  {
                    "session_key": "draft.2.retry",
                    "kind": "retry",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "s-draft",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.2.retry/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 0,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:22.926Z",
                    "ended_at": "2026-11-20T10:40:22.928Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.2.retry/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.2.retry/live.json"
                  }
                ]
              },
              "check": {
                "result": "PASS",
                "environmental": false,
                "duration_s": null,
                "output_path": null,
                "evidence": "ok"
              },
              "judge": {
                "sessions": [
                  {
                    "session_key": "draft.2.judge",
                    "kind": "judge",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "j",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.2.judge/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 1,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.036Z",
                    "ended_at": "2026-11-20T10:40:23.038Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.2.judge/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.2.judge/live.json"
                  }
                ],
                "criteria": [
                  {
                    "n": 1,
                    "id": "c-file",
                    "status": "MET"
                  }
                ],
                "met": 1,
                "total": 1,
                "gap": false,
                "blockers": [],
                "confidence": 0.8,
                "confidence_source": "judge",
                "guard": "clean"
              },
              "gate": {
                "verdict": "PROCEED",
                "route_target": "review",
                "token": "PROCEED",
                "guard": "clean"
              },
              "repeat_cause": null
            }
          ]
        },
        {
          "visit": 2,
          "entered_from": "back:review",
          "attempts": [
            {
              "attempt": 3,
              "item": null,
              "started_at": "2026-11-20T10:40:23.098Z",
              "ended_at": "2026-11-20T10:40:23.199Z",
              "step": {
                "sessions": [
                  {
                    "session_key": "draft.3.step",
                    "kind": "step",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "s-draft",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.3.step/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 0,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.098Z",
                    "ended_at": "2026-11-20T10:40:23.099Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.3.step/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.3.step/live.json"
                  }
                ]
              },
              "check": {
                "result": "PASS",
                "environmental": false,
                "duration_s": null,
                "output_path": null,
                "evidence": "ok"
              },
              "judge": {
                "sessions": [
                  {
                    "session_key": "draft.3.judge",
                    "kind": "judge",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "j",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.3.judge/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 1,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.190Z",
                    "ended_at": "2026-11-20T10:40:23.192Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.3.judge/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/draft.3.judge/live.json"
                  }
                ],
                "criteria": [
                  {
                    "n": 1,
                    "id": "c-file",
                    "status": "MET"
                  }
                ],
                "met": 1,
                "total": 1,
                "gap": false,
                "blockers": [],
                "confidence": 0.8,
                "confidence_source": "judge",
                "guard": "clean"
              },
              "gate": {
                "verdict": "PROCEED",
                "route_target": "review",
                "token": "PROCEED",
                "guard": "clean"
              },
              "repeat_cause": null
            }
          ]
        }
      ],
      "cost": {
        "reported": 0.06,
        "estimated": null,
        "figure": 0.06,
        "completeness": "complete"
      },
      "duration_s": 0.364,
      "share": 0.6
    },
    {
      "name": "review",
      "state": "paused",
      "visits": [
        {
          "visit": 1,
          "entered_from": "proceed",
          "attempts": [
            {
              "attempt": 1,
              "item": null,
              "started_at": "2026-11-20T10:40:23.056Z",
              "ended_at": "2026-11-20T10:40:23.087Z",
              "step": {
                "sessions": [
                  {
                    "session_key": "review.1.step",
                    "kind": "step",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "s-review",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.1.step/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 0,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.056Z",
                    "ended_at": "2026-11-20T10:40:23.057Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.1.step/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.1.step/live.json"
                  }
                ]
              },
              "check": {
                "result": "PASS",
                "environmental": false,
                "duration_s": null,
                "output_path": null,
                "evidence": null
              },
              "judge": {
                "sessions": [
                  {
                    "session_key": "review.1.judge",
                    "kind": "judge",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "j",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.1.judge/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 1,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.081Z",
                    "ended_at": "2026-11-20T10:40:23.082Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.1.judge/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.1.judge/live.json"
                  }
                ],
                "criteria": [
                  {
                    "n": 1,
                    "id": "c-review",
                    "status": "UNMET"
                  }
                ],
                "met": 0,
                "total": 1,
                "gap": false,
                "blockers": [
                  {
                    "id": "c-review",
                    "evidence": null,
                    "fix": null
                  }
                ],
                "confidence": 0.8,
                "confidence_source": "judge",
                "guard": "clean"
              },
              "gate": {
                "verdict": "BACK",
                "route_target": "draft",
                "token": "BACK",
                "guard": "clean"
              },
              "repeat_cause": null
            }
          ]
        },
        {
          "visit": 2,
          "entered_from": "proceed",
          "attempts": [
            {
              "attempt": 2,
              "item": null,
              "started_at": "2026-11-20T10:40:23.211Z",
              "ended_at": "2026-11-20T10:40:23.248Z",
              "step": {
                "sessions": [
                  {
                    "session_key": "review.2.step",
                    "kind": "step",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "s-review",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.2.step/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 0,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.211Z",
                    "ended_at": "2026-11-20T10:40:23.212Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.2.step/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.2.step/live.json"
                  }
                ]
              },
              "check": {
                "result": "PASS",
                "environmental": false,
                "duration_s": null,
                "output_path": null,
                "evidence": null
              },
              "judge": {
                "sessions": [
                  {
                    "session_key": "review.2.judge",
                    "kind": "judge",
                    "executor": "claude",
                    "alias": "inherit",
                    "model": null,
                    "session_id": "j",
                    "transcript": {
                      "engine": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.2.judge/raw.jsonl",
                      "native": null,
                      "native_kind": null
                    },
                    "usage": {
                      "input_tokens": 100,
                      "output_tokens": 50,
                      "cache_read_tokens": null,
                      "cache_write_tokens": null,
                      "thinking_tokens": null,
                      "reported_cost_usd": 0.01,
                      "estimated_cost_usd": null,
                      "by_model": {},
                      "turns": 1,
                      "peak_context_tokens": null
                    },
                    "tool_calls": 1,
                    "outcome": {
                      "ok": true,
                      "timed_out": false,
                      "stalled": false,
                      "partial": null,
                      "infra_cause": null,
                      "error_kind": null
                    },
                    "started_at": "2026-11-20T10:40:23.240Z",
                    "ended_at": "2026-11-20T10:40:23.241Z",
                    "activity_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.2.judge/activity.jsonl",
                    "live_path": "/work/repo/.tempergraph/runs/demo/T-1/sessions/review.2.judge/live.json"
                  }
                ],
                "criteria": [
                  {
                    "n": 1,
                    "id": "c-review",
                    "status": "UNVERIFIABLE"
                  }
                ],
                "met": 0,
                "total": 1,
                "gap": false,
                "blockers": [
                  {
                    "id": "c-review",
                    "evidence": "UNVERIFIABLE: missing",
                    "fix": null
                  }
                ],
                "confidence": 0.8,
                "confidence_source": "judge",
                "guard": "clean"
              },
              "gate": {
                "verdict": "ESCALATE",
                "route_target": "human",
                "token": "ESCALATE",
                "guard": "clean"
              },
              "repeat_cause": null
            }
          ]
        }
      ],
      "cost": {
        "reported": 0.04,
        "estimated": null,
        "figure": 0.04,
        "completeness": "complete"
      },
      "duration_s": 0.068,
      "share": 0.4
    }
  ],
  "pause": {
    "unit": "review",
    "kind": "escalation",
    "question": "unresolved_gap",
    "artifacts": [
      {
        "key": "verdict",
        "path": null
      }
    ],
    "decisions": [
      "proceed",
      "retry",
      "back:draft",
      "stop"
    ],
    "resume": [
      "tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
    ],
    "waiting_since": "2026-11-20T10:40:23.249Z",
    "waiting_s": 0.0
  },
  "budgets": {
    "counters": {
      "draft.retries": {
        "used": 0,
        "limit": 2
      },
      "review.retries": {
        "used": 0,
        "limit": 2
      },
      "review.loops.draft": {
        "used": 1,
        "limit": 1
      }
    },
    "run_cost_cap": {
      "limit": null,
      "left": null
    }
  },
  "health": {
    "alive": false,
    "silent_s": 0.0,
    "suspect_stall": false,
    "orphaned": false,
    "waiting_for_person_s": 0.0,
    "burn_usd_per_h": 721.4429,
    "cap_eta_min": null
  },
  "supervision": {
    "touches": [],
    "record": {
      "touches": {
        "designed": {
          "person": 0,
          "agent": 0,
          "unknown": 0,
          "pipeline": 0,
          "orchestrator": 0,
          "scheduler": 0,
          "engine": 0
        },
        "rescue": {
          "person": 0,
          "agent": 0,
          "unknown": 0,
          "pipeline": 0,
          "orchestrator": 0,
          "scheduler": 0,
          "engine": 0
        },
        "steer": {
          "person": 0,
          "agent": 0,
          "unknown": 0,
          "pipeline": 0,
          "orchestrator": 0,
          "scheduler": 0,
          "engine": 0
        },
        "engine": {
          "person": 0,
          "agent": 0,
          "unknown": 0,
          "pipeline": 0,
          "orchestrator": 0,
          "scheduler": 0,
          "engine": 0
        },
        "rescue_by_pause": {}
      },
      "undesigned": 0,
      "relayed": {
        "turn_named": 0,
        "turn_only": 0,
        "claimed": 0
      },
      "agent_own_rescues": 0,
      "wait_s": {},
      "person_wait_s": 0.0,
      "latency_s": null,
      "observations": null,
      "supervisors": {
        "sessions": 0,
        "hosts": []
      },
      "callers_unknown": 0,
      "supervision_cost": null,
      "supervision_share": null,
      "level": "observer",
      "level_by": "none",
      "kind": "supervision",
      "ts": "2026-11-20T10:40:23.257Z",
      "seq": 54,
      "thread_id": "demo/T-1",
      "segment": 0,
      "unit": null,
      "item": null,
      "attempt": null,
      "session_key": null
    },
    "hosts": [],
    "level": "observer",
    "level_by": "none",
    "designed_by": null,
    "cost": null
  },
  "events_tail": [
    "4 2026-11-20T10:40:22.768Z entered draft (visit 1, from start)",
    "8 2026-11-20T10:40:22.899Z check draft: PASS",
    "13 2026-11-20T10:40:22.919Z gate draft: RETRY -> draft",
    "17 2026-11-20T10:40:23.025Z check draft: PASS",
    "22 2026-11-20T10:40:23.043Z gate draft: PROCEED -> review",
    "23 2026-11-20T10:40:23.051Z entered review (visit 1, from proceed)",
    "27 2026-11-20T10:40:23.072Z check review: PASS",
    "32 2026-11-20T10:40:23.087Z gate review: BACK -> draft",
    "33 2026-11-20T10:40:23.093Z entered draft (visit 2, from back:review)",
    "37 2026-11-20T10:40:23.181Z check draft: PASS",
    "42 2026-11-20T10:40:23.199Z gate draft: PROCEED -> review",
    "43 2026-11-20T10:40:23.206Z entered review (visit 2, from proceed)",
    "47 2026-11-20T10:40:23.230Z check review: PASS",
    "52 2026-11-20T10:40:23.248Z gate review: ESCALATE -> human",
    "53 2026-11-20T10:40:23.249Z paused at review (escalation): tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
  ],
  "truncated": []
} as const

export const statsLive = {
  "schema_version": 1,
  "source": "home",
  "machines": [
    {
      "machine_id": "10bb793e-f65b-4c37-a80d-4a4264f43f03",
      "label": "laptop-a",
      "at": "2026-11-20T10:40:23.788Z",
      "age_s": -0.0,
      "stale": false,
      "this_machine": true
    },
    {
      "machine_id": "7907d54a-5e04-4773-bbaa-12d7db6926b8",
      "label": "desk-b",
      "at": "2026-11-20T10:40:23.512Z",
      "age_s": 0.3,
      "stale": false,
      "this_machine": false
    }
  ],
  "runs": [
    {
      "workflow": "demo",
      "alias": null,
      "state": "paused",
      "unit": "review",
      "attempt": 2,
      "estimated_cost_usd": null,
      "waiting_for_person_s": 0.5,
      "waiting_on": "person",
      "thread_id": "demo/T-1",
      "machine_id": "10bb793e-f65b-4c37-a80d-4a4264f43f03",
      "label": "laptop-a",
      "stale": false
    },
    {
      "workflow": "demo",
      "alias": null,
      "state": "paused",
      "unit": "draft",
      "attempt": 1,
      "estimated_cost_usd": null,
      "waiting_for_person_s": 0.3,
      "waiting_on": "person",
      "thread_id": "demo/T-8",
      "machine_id": "10bb793e-f65b-4c37-a80d-4a4264f43f03",
      "label": "laptop-a",
      "stale": false
    },
    {
      "thread_hash": "569e6dd70dac85192ea53cf102718f33",
      "repo_id": "149cfaa307c915348598cbf35a398afb",
      "workflow": "demo",
      "alias": null,
      "state": "paused",
      "unit": "review",
      "attempt": 2,
      "estimated_cost_usd": null,
      "waiting_for_person_s": 0.6,
      "waiting_on": "person",
      "machine_id": "7907d54a-5e04-4773-bbaa-12d7db6926b8",
      "label": "desk-b",
      "stale": false
    },
    {
      "thread_hash": "502733bcb6639b57ba733390eedcd076",
      "repo_id": "149cfaa307c915348598cbf35a398afb",
      "workflow": "demo",
      "alias": null,
      "state": "paused",
      "unit": "draft",
      "attempt": 1,
      "estimated_cost_usd": null,
      "waiting_for_person_s": 0.3,
      "waiting_on": "person",
      "machine_id": "7907d54a-5e04-4773-bbaa-12d7db6926b8",
      "label": "desk-b",
      "stale": false
    }
  ]
} as const

export const statsMachine = {
  "schema_version": 1,
  "source": "home",
  "month": "2026-11",
  "since": null,
  "totals": {
    "runs": 2,
    "threads": 2,
    "reported_usd": 0.06,
    "estimated_usd": null,
    "completeness": "complete",
    "lower_bound": false,
    "exits": {
      "0": 1,
      "3": 1
    }
  },
  "unknown_schema": 0,
  "synced": {
    "team": {
      "synced_at": "2026-11-20T10:40:23.770Z",
      "machines": {
        "10bb793e-f65b-4c37-a80d-4a4264f43f03": {
          "label": "laptop-a",
          "synced_at": "2026-11-20T10:40:23.770Z",
          "rows": 1,
          "ago_s": 0.0
        },
        "7907d54a-5e04-4773-bbaa-12d7db6926b8": {
          "label": "desk-b",
          "synced_at": "2026-11-20T10:40:23.770Z",
          "rows": 1,
          "ago_s": 0.0
        }
      }
    }
  },
  "by": {
    "key": "machine",
    "groups": {
      "desk-b (7907d54a)": {
        "runs": 1,
        "threads": 1,
        "reported_usd": 0.02,
        "estimated_usd": null,
        "completeness": "complete",
        "lower_bound": false,
        "exits": {
          "3": 1
        }
      },
      "laptop-a (10bb793e)": {
        "runs": 1,
        "threads": 1,
        "reported_usd": 0.04,
        "estimated_usd": null,
        "completeness": "complete",
        "lower_bound": false,
        "exits": {
          "0": 1
        }
      }
    }
  }
} as const

export const statsProjection = {
  "schema_version": 1,
  "source": "home",
  "month": null,
  "since": null,
  "totals": {
    "runs": 2,
    "threads": 2,
    "reported_usd": 0.06,
    "estimated_usd": null,
    "completeness": "complete",
    "lower_bound": false,
    "exits": {
      "0": 1,
      "3": 1
    }
  },
  "unknown_schema": 0,
  "synced": {
    "team": {
      "synced_at": "2026-11-20T10:40:23.770Z",
      "machines": {
        "10bb793e-f65b-4c37-a80d-4a4264f43f03": {
          "label": "laptop-a",
          "synced_at": "2026-11-20T10:40:23.770Z",
          "rows": 1,
          "ago_s": 0.0
        },
        "7907d54a-5e04-4773-bbaa-12d7db6926b8": {
          "label": "desk-b",
          "synced_at": "2026-11-20T10:40:23.770Z",
          "rows": 1,
          "ago_s": 0.0
        }
      }
    }
  },
  "by": {
    "key": "workflow",
    "groups": {
      "demo": {
        "runs": 2,
        "threads": 2,
        "reported_usd": 0.06,
        "estimated_usd": null,
        "completeness": "complete",
        "lower_bound": false,
        "exits": {
          "0": 1,
          "3": 1
        }
      }
    }
  },
  "projection": [
    {
      "workflow": "demo",
      "runs": 1,
      "median_usd": 0.04,
      "p90_usd": 0.04,
      "thin": true
    }
  ]
} as const
