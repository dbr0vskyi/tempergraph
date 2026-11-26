```mermaid
flowchart TD
  start((start))
  u0["prepare"]
  u1["setup_route"]
  u2["list_components"]
  u3["read_component<br/>Read one component folder; report findings"]
  u4["setup<br/>Write the overview spec and one spec per component"]
  u5["triage<br/>Read the task, find the gaps, pick the route"]
  u6["discovery_short<br/>Confirm the cited behaviours; write the hand-off"]
  u7["owner_questions"]
  u8["ask_route"]
  u9["ask_owner"]
  u10["read_gap<br/>Read one gap's documents and code; report findings"]
  u11["discovery<br/>Close each gap with a spec, record or research note"]
  u12["plan<br/>Design requirements and phases; state complexity"]
  u13["code_mode"]
  u14["expand<br/>Write task rows and verification for a complex plan"]
  u15["phase<br/>Build one phase of the plan, tests first, and commit it"]
  u16["code<br/>Build the plan test first in one session"]
  u17["code_join"]
  u18["independent_review<br/>Read the change as an independent reader; write numbered findings"]
  u19["outcome<br/>outcome gate"]
  fin([finalizer])
  stop((end))
  start --> u0
  u0 --> u1
  u1 --> u2
  u1 --> u5
  u2 --> u3
  u3 --> u4
  u4 --> u5
  u5 --> u6
  u5 --> u7
  u5 --> u12
  u5 --> u16
  u6 --> u10
  u6 --> u12
  u7 --> u8
  u8 --> u9
  u8 --> u10
  u9 --> u10
  u10 --> u11
  u11 --> u12
  u11 --> u19
  u12 --> u13
  u12 -.->|back| u11
  u13 --> u16
  u13 --> u14
  u14 --> u15
  u14 -.->|back| u12
  u14 -.->|back| u11
  u15 --> u16
  u16 --> u17
  u16 -.->|back| u12
  u16 -.->|back| u11
  u16 -.->|back| u5
  u17 --> u18
  u17 --> u19
  u18 --> u19
  u18 -.->|back| u12
  u18 -.->|back| u16
  u19 --> fin
  u19 -.->|back| u3
  u19 -.->|back| u4
  u19 -.->|back| u5
  u19 -.->|back| u6
  u19 -.->|back| u10
  u19 -.->|back| u11
  u19 -.->|back| u12
  u19 -.->|back| u14
  u19 -.->|back| u15
  u19 -.->|back| u16
  u19 -.->|back| u18
  fin --> stop

```
