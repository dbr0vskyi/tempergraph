// Written by make_fixtures.py; do not edit. The same documents as the .json files beside it.

export const status = {
  "schema_version": 1,
  "generated_at": "2026-11-20T10:06:34.458Z",
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
  "generated_at": "2026-11-20T10:06:34.468Z",
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
    "workspace": {
      "mode": "worktree",
      "path": "/work/repo.worktrees/demo--T-1",
      "branch": "tg/demo/T-1",
      "state": "active"
    },
    "exit_code": 3,
    "exit_reason": "escalation",
    "segment": 0,
    "last_seq": 54,
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
              "started_at": "2026-11-20T10:06:33.941Z",
              "ended_at": "2026-11-20T10:06:34.081Z",
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
                    "started_at": "2026-11-20T10:06:33.941Z",
                    "ended_at": "2026-11-20T10:06:33.943Z",
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
                    "started_at": "2026-11-20T10:06:34.074Z",
                    "ended_at": "2026-11-20T10:06:34.076Z",
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
              "started_at": "2026-11-20T10:06:34.088Z",
              "ended_at": "2026-11-20T10:06:34.196Z",
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
                    "started_at": "2026-11-20T10:06:34.088Z",
                    "ended_at": "2026-11-20T10:06:34.089Z",
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
                    "started_at": "2026-11-20T10:06:34.188Z",
                    "ended_at": "2026-11-20T10:06:34.190Z",
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
              "started_at": "2026-11-20T10:06:34.258Z",
              "ended_at": "2026-11-20T10:06:34.385Z",
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
                    "started_at": "2026-11-20T10:06:34.258Z",
                    "ended_at": "2026-11-20T10:06:34.260Z",
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
                    "started_at": "2026-11-20T10:06:34.378Z",
                    "ended_at": "2026-11-20T10:06:34.379Z",
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
      "duration_s": 0.375,
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
              "started_at": "2026-11-20T10:06:34.208Z",
              "ended_at": "2026-11-20T10:06:34.245Z",
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
                    "started_at": "2026-11-20T10:06:34.208Z",
                    "ended_at": "2026-11-20T10:06:34.210Z",
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
                    "started_at": "2026-11-20T10:06:34.238Z",
                    "ended_at": "2026-11-20T10:06:34.240Z",
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
              "started_at": "2026-11-20T10:06:34.396Z",
              "ended_at": "2026-11-20T10:06:34.433Z",
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
                    "started_at": "2026-11-20T10:06:34.396Z",
                    "ended_at": "2026-11-20T10:06:34.398Z",
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
                    "started_at": "2026-11-20T10:06:34.426Z",
                    "ended_at": "2026-11-20T10:06:34.428Z",
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
      "duration_s": 0.074,
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
    "waiting_since": "2026-11-20T10:06:34.434Z",
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
    "burn_usd_per_h": 697.6744,
    "cap_eta_min": null
  },
  "supervision": {
    "touches": [],
    "record": null,
    "hosts": null,
    "level": null,
    "cost": null
  },
  "events_tail": [
    "4 2026-11-20T10:06:33.935Z entered draft (visit 1, from start)",
    "8 2026-11-20T10:06:34.063Z check draft: PASS",
    "13 2026-11-20T10:06:34.081Z gate draft: RETRY -> draft",
    "17 2026-11-20T10:06:34.178Z check draft: PASS",
    "22 2026-11-20T10:06:34.196Z gate draft: PROCEED -> review",
    "23 2026-11-20T10:06:34.203Z entered review (visit 1, from proceed)",
    "27 2026-11-20T10:06:34.228Z check review: PASS",
    "32 2026-11-20T10:06:34.245Z gate review: BACK -> draft",
    "33 2026-11-20T10:06:34.252Z entered draft (visit 2, from back:review)",
    "37 2026-11-20T10:06:34.366Z check draft: PASS",
    "42 2026-11-20T10:06:34.385Z gate draft: PROCEED -> review",
    "43 2026-11-20T10:06:34.391Z entered review (visit 2, from proceed)",
    "47 2026-11-20T10:06:34.416Z check review: PASS",
    "52 2026-11-20T10:06:34.433Z gate review: ESCALATE -> human",
    "53 2026-11-20T10:06:34.434Z paused at review (escalation): tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
  ],
  "truncated": []
} as const
