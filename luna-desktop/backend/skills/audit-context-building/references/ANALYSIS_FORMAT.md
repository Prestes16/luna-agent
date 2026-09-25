# Luna Audit Context — Analysis Format

Use one record per relevant function, handler, instruction, endpoint, parser, state transition or equivalent unit.

```text
UNIT
Identity:
Location:
Language/domain:
Reachability / caller:

PURPOSE
Observed responsibility:
Inputs:
Outputs:
State read:
State written:

AUTHORITY & TRUST
Caller-controlled values:
Externally-controlled values:
Privilege/identity assumptions:
Trust boundary crossed:
Authorization/authentication dependency:

CONTRACT
Preconditions:
Postconditions:
Invariants expected:
Error/failure paths:
Rollback/cleanup behavior:

DEPENDENCIES
Calls:
For each call:
  - callee:
  - property expected from callee:
  - evidence that property is established:
  - status: confirmed | partial | opaque | nada encontrado

DATA / REPRESENTATION
Types:
Units/base units:
Bounds:
Rounding/conversion:
Serialization/parsing:

ASSUMPTIONS
- assumption:
  enforcement:
  evidence:

OPEN QUESTIONS
- ...

EVIDENCE
- file:function:line-range -> observed fact
```

Rules:
- A function name is not evidence of behavior.
- A successful path is not evidence for failure paths.
- Client-side checks do not prove server-side enforcement.
- `nada encontrado` means exactly that: no enforcement was found in the inspected evidence.
- Contradictory evidence remains explicit until additional evidence resolves it.
