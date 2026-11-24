```mermaid
flowchart TD
  start((start))
  u0["prepare"]
  u1["setup_route"]
  u2["setup<br/>Write the overview spec and one spec per component"]
  u3["triage<br/>Read the task, find the gaps, pick the route"]
  u4["discovery_short<br/>Confirm the cited behaviours; write the hand-off"]
  u5["discovery<br/>Close each gap with a spec, record or research note"]
  u6["plan<br/>Design requirements and phases; state complexity"]
  u7["code_mode"]
  u8["expand<br/>Write task rows and verification for a complex plan"]
  u9["code<br/>Build the plan test first in one session"]
  u10["code_join"]
  u11["outcome<br/>outcome gate"]
  fin([finalizer])
  stop((end))
  start --> u0
  u0 --> u1
  u1 --> u2
  u1 --> u3
  u2 --> u3
  u3 --> u4
  u3 --> u5
  u3 --> u6
  u3 --> u9
  u4 --> u5
  u4 --> u6
  u5 --> u6
  u5 --> u11
  u6 --> u7
  u6 -.->|back| u5
  u7 --> u9
  u7 --> u8
  u8 --> u9
  u8 -.->|back| u6
  u8 -.->|back| u5
  u9 --> u10
  u9 -.->|back| u6
  u9 -.->|back| u5
  u9 -.->|back| u3
  u10 --> u11
  u11 --> fin
  u11 -.->|back| u2
  u11 -.->|back| u3
  u11 -.->|back| u4
  u11 -.->|back| u5
  u11 -.->|back| u6
  u11 -.->|back| u8
  u11 -.->|back| u9
  fin --> stop

```
