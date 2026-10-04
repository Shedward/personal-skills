---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: true
---

Run a `/grilling` session, using the `/domain-modeling` skill.

<!-- ═══ BEGIN LOCAL CUSTOMIZATIONS ═══
     Личные надстройки поверх базового скилла.
     При обновлении скилла сохранить этот блок целиком (merge вручную). -->

## Where docs live (override for /domain-modeling file structure)

Do NOT create `CONTEXT.md` or `docs/adr/` inside the repository — the user
keeps several working copies of each repo, so repo-local docs would diverge.
Store the artifacts in a shared per-project location outside any working copy:

```
~/.claude/docs/<project>/CONTEXT.md
~/.claude/docs/<project>/adr/NNNN-title.md
~/.claude/docs/<project>/maps/<subsystem>.md   # subsystem maps, owned by /map-subsystem
```

`<project>` is the canonical project name (e.g. `ios-apps`, `Levitan`), not
the working-copy directory name. Always check that directory for existing
docs before writing new ones, regardless of which working copy is open.

<!-- ═══ END LOCAL CUSTOMIZATIONS ═══ -->
