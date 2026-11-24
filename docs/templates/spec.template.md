# <Capability name>

## Purpose

One short paragraph: what the capability is for and who depends on it.

## Behaviours

### SES-B1 Idle sessions end

WHEN a session has been idle for 30 minutes THE service SHALL end the session.

- GIVEN a session idle for 31 minutes WHEN a request arrives THEN the request is refused as signed out
- GIVEN a session idle for 29 minutes WHEN a request arrives THEN the request is served

## Acceptance criteria

- SES-AC1 (SES-B1): A request on a session idle for 31 minutes is refused as signed out
