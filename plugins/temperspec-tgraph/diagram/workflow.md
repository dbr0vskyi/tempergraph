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
  u7["read_gap<br/>Read one gap's documents and code; report findings"]
  u8["discovery<br/>Close each gap with a spec, record or research note"]
  u9["plan<br/>Design requirements and phases; state complexity"]
  u10["expand<br/>Write task rows and verification for a complex plan"]
  u11["code<br/>Build the plan test first in one session"]
  u12["outcome<br/>outcome gate"]
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
  u5 --> u9
  u5 --> u11
  u6 --> u7
  u6 --> u9
  u7 --> u8
  u8 --> u9
  u8 --> u12
  u9 --> u10
  u9 --> u11
  u9 -.->|back| u8
  u10 --> u11
  u10 -.->|back| u9
  u10 -.->|back| u8
  u11 --> u12
  u11 -.->|back| u9
  u11 -.->|back| u8
  u11 -.->|back| u5
  u12 --> fin
  u12 -.->|back| u3
  u12 -.->|back| u4
  u12 -.->|back| u5
  u12 -.->|back| u6
  u12 -.->|back| u7
  u12 -.->|back| u8
  u12 -.->|back| u9
  u12 -.->|back| u10
  u12 -.->|back| u11
  fin --> stop

```
