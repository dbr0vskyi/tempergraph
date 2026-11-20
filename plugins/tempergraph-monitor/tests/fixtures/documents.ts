// Written by make_fixtures.py; do not edit. The same documents as the .json files beside it.

export const status = {
  "schema_version": 1,
  "generated_at": "2026-11-20T17:51:30.985Z",
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
  "generated_at": "2026-11-20T17:51:30.997Z",
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
    "last_seq": 59,
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
              "started_at": "2026-11-20T17:51:30.314Z",
              "ended_at": "2026-11-20T17:51:30.468Z",
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
                    "started_at": "2026-11-20T17:51:30.314Z",
                    "ended_at": "2026-11-20T17:51:30.316Z",
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
                    "started_at": "2026-11-20T17:51:30.459Z",
                    "ended_at": "2026-11-20T17:51:30.461Z",
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
                    "evidence": "UNMET: missing",
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
              "started_at": "2026-11-20T17:51:30.477Z",
              "ended_at": "2026-11-20T17:51:30.644Z",
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
                    "started_at": "2026-11-20T17:51:30.477Z",
                    "ended_at": "2026-11-20T17:51:30.479Z",
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
                    "started_at": "2026-11-20T17:51:30.635Z",
                    "ended_at": "2026-11-20T17:51:30.638Z",
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
              "started_at": "2026-11-20T17:51:30.714Z",
              "ended_at": "2026-11-20T17:51:30.865Z",
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
                    "started_at": "2026-11-20T17:51:30.714Z",
                    "ended_at": "2026-11-20T17:51:30.716Z",
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
                    "started_at": "2026-11-20T17:51:30.856Z",
                    "ended_at": "2026-11-20T17:51:30.858Z",
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
      "duration_s": 0.472,
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
              "started_at": "2026-11-20T17:51:30.657Z",
              "ended_at": "2026-11-20T17:51:30.701Z",
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
                    "started_at": "2026-11-20T17:51:30.657Z",
                    "ended_at": "2026-11-20T17:51:30.659Z",
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
                    "started_at": "2026-11-20T17:51:30.692Z",
                    "ended_at": "2026-11-20T17:51:30.694Z",
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
                    "evidence": "UNMET: missing",
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
              "started_at": "2026-11-20T17:51:30.879Z",
              "ended_at": "2026-11-20T17:51:30.924Z",
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
                    "started_at": "2026-11-20T17:51:30.879Z",
                    "ended_at": "2026-11-20T17:51:30.881Z",
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
                    "started_at": "2026-11-20T17:51:30.915Z",
                    "ended_at": "2026-11-20T17:51:30.918Z",
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
      "duration_s": 0.089,
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
    "waiting_since": "2026-11-20T17:51:30.925Z",
    "waiting_s": 0.1
  },
  "budgets": {
    "counters": {
      "draft.retries": {
        "used": 1,
        "limit": 2,
        "cause": "blockers"
      },
      "review.retries": {
        "used": 0,
        "limit": 2
      },
      "review.loops.draft": {
        "used": 1,
        "limit": 1
      },
      "review.loops:draft": {
        "used": 1,
        "limit": 1,
        "cause": "defect_in"
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
    "waiting_for_person_s": 0.1,
    "burn_usd_per_h": 561.6225,
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
      "ts": "2026-11-20T17:51:30.931Z",
      "seq": 57,
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
    "5 2026-11-20T17:51:30.301Z entered draft (visit 1, from start)",
    "9 2026-11-20T17:51:30.442Z check draft: PASS",
    "14 2026-11-20T17:51:30.468Z gate draft: RETRY -> draft",
    "15 2026-11-20T17:51:30.468Z budget retries: 1/2 (blockers)",
    "19 2026-11-20T17:51:30.620Z check draft: PASS",
    "24 2026-11-20T17:51:30.644Z gate draft: PROCEED -> review",
    "25 2026-11-20T17:51:30.651Z entered review (visit 1, from proceed)",
    "29 2026-11-20T17:51:30.678Z check review: PASS",
    "34 2026-11-20T17:51:30.701Z gate review: BACK -> draft",
    "35 2026-11-20T17:51:30.701Z budget loops:draft: 1/1 (defect_in)",
    "36 2026-11-20T17:51:30.708Z entered draft (visit 2, from back:review)",
    "40 2026-11-20T17:51:30.840Z check draft: PASS",
    "45 2026-11-20T17:51:30.865Z gate draft: PROCEED -> review",
    "46 2026-11-20T17:51:30.872Z entered review (visit 2, from proceed)",
    "50 2026-11-20T17:51:30.902Z check review: PASS",
    "55 2026-11-20T17:51:30.924Z gate review: ESCALATE -> human",
    "56 2026-11-20T17:51:30.925Z paused at review (escalation): tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
  ],
  "truncated": []
} as const

export const statsLive = {
  "schema_version": 1,
  "source": "home",
  "machines": [
    {
      "machine_id": "70ddb97d-b454-4d26-8eb5-c2b6211b8298",
      "label": "laptop-a",
      "at": "2026-11-20T17:51:31.653Z",
      "age_s": -0.0,
      "stale": false,
      "this_machine": true
    },
    {
      "machine_id": "bbc88313-0b2e-4837-b32b-65080eae2c9b",
      "label": "desk-b",
      "at": "2026-11-20T17:51:31.239Z",
      "age_s": 0.4,
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
      "waiting_for_person_s": 0.7,
      "waiting_on": "person",
      "thread_id": "demo/T-1",
      "machine_id": "70ddb97d-b454-4d26-8eb5-c2b6211b8298",
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
      "waiting_for_person_s": 0.4,
      "waiting_on": "person",
      "thread_id": "demo/T-8",
      "machine_id": "70ddb97d-b454-4d26-8eb5-c2b6211b8298",
      "label": "laptop-a",
      "stale": false
    },
    {
      "thread_hash": "cc25b9e321f53089afc590876e9ddd13",
      "repo_id": "7e92fb78c43c6ea813c62b74ba526aaf",
      "workflow": "demo",
      "alias": null,
      "state": "paused",
      "unit": "review",
      "attempt": 2,
      "estimated_cost_usd": null,
      "waiting_for_person_s": 0.7,
      "waiting_on": "person",
      "machine_id": "bbc88313-0b2e-4837-b32b-65080eae2c9b",
      "label": "desk-b",
      "stale": false
    },
    {
      "thread_hash": "fba08be97c7da6cb3eb1b0387f5be5c3",
      "repo_id": "7e92fb78c43c6ea813c62b74ba526aaf",
      "workflow": "demo",
      "alias": null,
      "state": "paused",
      "unit": "draft",
      "attempt": 1,
      "estimated_cost_usd": null,
      "waiting_for_person_s": 0.4,
      "waiting_on": "person",
      "machine_id": "bbc88313-0b2e-4837-b32b-65080eae2c9b",
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
      "synced_at": "2026-11-20T17:51:31.581Z",
      "machines": {
        "70ddb97d-b454-4d26-8eb5-c2b6211b8298": {
          "label": "laptop-a",
          "synced_at": "2026-11-20T17:51:31.581Z",
          "rows": 1,
          "ago_s": 0.1
        },
        "bbc88313-0b2e-4837-b32b-65080eae2c9b": {
          "label": "desk-b",
          "synced_at": "2026-11-20T17:51:31.581Z",
          "rows": 1,
          "ago_s": 0.1
        }
      }
    }
  },
  "duplicate_row_ids": [],
  "by": {
    "key": "machine",
    "groups": {
      "desk-b (bbc88313)": {
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
      "laptop-a (70ddb97d)": {
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
      "synced_at": "2026-11-20T17:51:31.581Z",
      "machines": {
        "70ddb97d-b454-4d26-8eb5-c2b6211b8298": {
          "label": "laptop-a",
          "synced_at": "2026-11-20T17:51:31.581Z",
          "rows": 1,
          "ago_s": 0.1
        },
        "bbc88313-0b2e-4837-b32b-65080eae2c9b": {
          "label": "desk-b",
          "synced_at": "2026-11-20T17:51:31.581Z",
          "rows": 1,
          "ago_s": 0.1
        }
      }
    }
  },
  "duplicate_row_ids": [],
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
