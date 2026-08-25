# Parallel Worktree Round — Operational Notes

Durable conventions for running a CMIG development round (round-7/8 style:
one coordinator session reviewing and integrating, N codex workers in Orca
worktrees). Each round's briefs live in `REVIEW/round<N>/`; this file holds
what stays true between rounds, with the incidents that taught each rule.

## Worker launch command

```text
codex -a never --sandbox workspace-write -c check_for_update_on_startup=false
```

- `-a never` — approvals would stall an unattended worker; failures return to
  the model.
- `--sandbox workspace-write` — grant `-c sandbox_workspace_write.network_access=true`
  per track only when the brief needs downloads (round 7: dependency install,
  human-GEM fetch).
- `-c check_for_update_on_startup=false` — **required**. Round-8 incident: with
  the default `true`, one of six simultaneously starting TUIs ran the updater
  (`npm install -g @openai/codex`, 0.148.0 → 0.149.1), which replaced the
  binaries under every RUNNING codex process. All six workers lost their tool
  host (`codex-code-mode-host is missing at its configured path`) and had to be
  restarted and re-prompted. The flag verifiably flips `codex doctor`'s
  "startup update check" to `false`. Update codex deliberately BETWEEN rounds
  (`codex update`), never let it happen mid-round. This is a per-invocation
  override; the user's interactive codex keeps its normal update behavior.

## Worker rules that earned their place

- **Workers run no git.** The codex sandbox blocks linked-worktree metadata
  (`.git/worktrees/<name>/index.lock` → `Operation not permitted`). Round-7
  workers wasted effort discovering this; since round 8 the common brief
  forbids all git commands and the coordinator commits after review.
- **Pre-sync each worktree venv sequentially** before dispatch
  (`uv sync --all-extras --group dev`, `UV_HTTP_TIMEOUT=180`). Six parallel
  all-extras syncs saturated the network in round 7 (3/6 timed out). Workers
  then use `uv run --no-sync` only. The sandbox cannot read `~/.cache/uv`
  (its `sdists-v9/.git` path); workers set a task-local `UV_CACHE_DIR=/tmp/...`.
- **Completion signal = the report file** (`REVIEW/round<N>/report_<id>.md`)
  appearing in the worktree, plus a frozen-screen fallback (~6 min unchanged
  screen hash) and a terminal-death check. `orca terminal wait --for tui-idle`
  is NOT a completion signal — the codex TUI renders its input box while
  working, so the condition is satisfied immediately.
- **QtWebEngine cannot run in the worker sandbox** on macOS (Chromium Mach-port
  rendezvous → SIGTRAP/exit 133). Workers report it honestly; the coordinator
  re-runs the GUI test set on the host.
- GUI test files that build several `CmigMainWindow`s need deterministic Qt
  teardown (autouse fixture: close + deleteLater + processEvents), or the
  green run segfaults at interpreter exit (exit 139).

## Coordinator rules

- File-ownership partition per track, `cmig/cli/main.py` single-owner,
  dependency files frozen (or single-owner), hash-bearing modules
  (`workflow_manifest`/`golden`/envelope JSON) single-owner with the documented
  drift→re-bless procedure; solve-golden re-bless is its own single-owner grant.
- Per-track green is not integration green. Both rounds, the full randomized
  suite (`pytest -q -p randomly --randomly-seed=<recorded>`) at integration
  caught what disjoint ownership could not: monkeypatch semantics broken by an
  import-binding change (round 7), stale schema-version/caption/source-census
  pins and cross-track basis fallout (rounds 7–8). Run it before every merge to
  main, after `uv sync --reinstall-package cmig` (a stale installed wheel
  shadows the working tree on console-script paths).
- Gates per track and at integration: ruff clean, `mypy cmig` 0 errors,
  `cmig golden verify-envelope` unchanged (except granted evolutions),
  `cmig golden verify` on both solvers when goldens moved, owned tests green.
- Record everything in `REVIEW/round<N>/COORDINATOR_LOG.md` (round-5 convention)
  and keep per-track reports committed next to the briefs.
