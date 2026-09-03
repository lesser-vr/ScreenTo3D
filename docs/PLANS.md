# Execution plans

Complex work is tracked in `docs/exec-plans/active/`. Completed plans move to
`docs/exec-plans/completed/` without losing their decision or evidence log.

Each plan must be understandable without chat history and contain:

- outcome and non-goals;
- current repository facts;
- milestones ordered as independently verifiable vertical slices;
- acceptance checks and canonical commands;
- progress checklist;
- decisions with rationale;
- discoveries, risks, and rollback/recovery notes;
- final evidence and remaining debt.

Update the plan while implementing. If reality contradicts the plan, record the
discovery and change the plan before broadening the implementation.

Small, local changes may use a short inline plan in the task, but any change that
alters a mode contract, architecture boundary, media format, GPU ownership model,
or benchmark claim requires a checked-in execution plan.
