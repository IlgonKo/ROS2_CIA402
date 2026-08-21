# Motion Server Implementation Rules

## Design and contract boundaries

- Read the applicable `docs/decisions.md` entries and RF/TD detail document before implementation.
- For interface, protocol or capability work, identify the following before editing code:
  - public contract;
  - required implementation methods;
  - optional behavior;
  - internal helpers;
  - explicitly excluded scope.
- Do not promote an internal helper to a public or capability contract merely because it appears in the call hierarchy.
- Do not add required methods, capability requirements or externally visible behavior that the accepted decision does not specify.
- If implementation appears to require a broader contract, stop and update the design decision with the user before expanding scope.

## Contract verification

- Add a minimal conforming implementation test for every new interface or capability.
- Add a missing-required-member rejection test.
- Add a test proving that optional behavior and internal helpers are not required by the public contract.
- Before completing the work, compare each contract item with its implementation and test, and check explicitly for scope expansion.

## User changes

- Preserve unrelated user changes and do not include them in a task commit unless the user explicitly requests it.
