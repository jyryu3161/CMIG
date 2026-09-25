# Native CI fixture correction — design and independent review

Status: independent review accepted for native CI; fresh native Ubuntu 3.10 and Windows validation remains with the coordinator.

## Actual failure and evidence

Run `36108964125` at pushed `c0ff2b5` passes Ubuntu 3.12 and macOS, confirmed by `.run/remediation-20260925/harness-windows-ci/remote-ci-result.json`. Its Ubuntu 3.10 native log, `.run/remediation-20260925/harness-windows-ci/ubuntu310-failure.log`, fails all six real-CLI cases at `real_cli_fixture` when the newly copied `.venv/bin/python` runs `import site`. The interpreter reports `sys.base_prefix=/install`, looks for `/install/lib/python3.10`, and fails with `ModuleNotFoundError: No module named 'encodings'`. This is interpreter startup failure before the checker or harness behavior can run.

The completed Windows job `107987827162` has one failure: `test_windows_argv_uses_supplied_path_and_preserves_arguments` compares the path string returned by `shutil.which` (`sample.CMD`) against fixture spelling (`sample.cmd`). The native log `.run/remediation-20260925/harness-windows-ci/windows-failure.log` shows identical remaining arguments, including Korean text; both path spellings name the same native file. All six real-CLI cases, including shared-console cancellation, pass per the coordinator's native result. This is a test assertion defect; production path case must not be rewritten. Existing unrelated skips remain distinct from passes.

Read set: `AGENTS.md`; `REVIEW/remediation_harness_windows_ci_2026-09-25.md`; `tests/test_harness_execute.py`, specifically `real_cli_fixture` and its six callers; `tests/test_harness_checks.py` and `scripts/harness_checks.py` at `_windows_argv`; both native failure logs and the result JSON above; CPython 3.10 venv documentation and implementation. Existing checks/controller contracts are preserved rather than reopened.

The fixture currently forces `venv.EnvBuilder(with_pip=False, symlinks=False)` on every OS, then adds a macOS copied-dylib workaround. CPython's own venv CLI chooses symlinks outside Windows and copies on Windows; this differs from the `EnvBuilder` constructor default. The [CPython 3.10 source](https://raw.githubusercontent.com/python/cpython/3.10/Lib/venv/__init__.py) documents and implements this distinction. The [venv documentation](https://docs.python.org/3.10/library/venv.html#venv.EnvBuilder) supports both mechanisms and explains isolated environment creation.

Independent local probes under `.run/remediation-20260925/harness-native-review/` create real venvs in paths with spaces using installed uv-managed macOS Python 3.10.18 and synchronized project Python 3.12.11. Both symlinked venvs start successfully, import `encodings`, report the fixture path as `sys.prefix`, retain the installed runtime as `sys.base_prefix`, and use fixture-local site-packages. The copied baseline also succeeds on these macOS builds with its existing dylib workaround, so these probes do not reproduce Ubuntu's failure. They verify the selected supported mechanism locally; repairing the exact Linux 3.10 runtime remains a native CI acceptance requirement. Evidence: `probe_venv.py`, `probe310.jsonl`, and `probe312.jsonl`.

## Bounded Sol implementation contract

Sol reads the exact read set above and this report. Sol owns only `tests/test_harness_execute.py`, `tests/test_harness_checks.py`, and ignored `.run/remediation-20260925/harness-native-implementation/`; the reviewer alone owns this report and ignored `.run/remediation-20260925/harness-native-review/`. Root owns dispatch, Git operations and remote CI. Target one implementation/check pass within five minutes; independent review within five minutes of the frozen change and evidence.

1. In `real_cli_fixture`, select the native venv mechanism explicitly: `venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(root / ".venv")`. Add a short comment explaining that POSIX links preserve the uv-managed interpreter's runtime location while Windows retains copied native launchers.
2. Remove the now-obsolete macOS-only dylib-copy block. Symlinked POSIX interpreters resolve their actual runtime installation; copying a sibling library is unnecessary and obscures the selected mechanism.
3. Preserve the subsequent real fixture `.venv` interpreter launch, fixture-local `ruff.py`, six real subprocess cases, literal Korean report and byte-level round trip, paths with spaces, Windows `.cmd` launcher and console controller, cancellation/cleanup assertions, unauthorized Git/write assertions, and every existing test. Do not add a fake interpreter, global `PYTHONHOME`, `PYTHONPATH`, package/dependency/shared-environment changes, skip/xfail, timeout increases, or weakened assertions. No production or workflow edits are expected.
4. The six existing real-CLI cases provide direct startup and end-to-end coverage. Do not add a test that merely repeats the boolean expression. Capture a small scratch startup probe if additional interpreter evidence is useful, using installed runtimes without installing packages or changing the project environment.
5. In `test_windows_argv_uses_supplied_path_and_preserves_arguments`, replace the single full string-list comparison with `resolved = hc._windows_argv(argv, env)`, `assert Path(resolved[0]).samefile(command)`, and `assert resolved[1:] == argv[1:]`. Retain the explicit supplied PATH, fixture path with spaces, Korean argument and missing-command assertion unchanged. `Path.samefile` checks actual filesystem identity, so it does not weaken the executable selection requirement or normalize the argument payload. Python documents this operation in [Path.samefile](https://docs.python.org/3.10/library/pathlib.html#pathlib.Path.samefile). Do not modify `_windows_argv` production behavior.

Run these exact acceptance commands in the synchronized environment, recording exit codes and exact pass/skip counts:

```text
uv run --no-sync pytest -o addopts='' -q tests/test_harness_execute.py tests/test_harness_checks.py tests/test_harness_hooks.py
uv run --no-sync ruff check .
uv run --no-sync mypy cmig
uv run --no-sync python scripts/check_release_versions.py
uv run --no-sync cmig golden verify-envelope
```

Expected local macOS harness result is all 60 existing tests passed with zero skips; existing native Windows platform skips elsewhere are preserved and must be reported separately. No full-suite run by Sol or the reviewer. Preserve pre-existing edits and report the final diff, file digests and evidence paths to root; do not commit or push. Root must validate the corrected native Ubuntu 3.10 real-CLI cases and Windows file-identity assertion through CI, and must report any new actual native failure before expanding this contract.

## Independent implementation review

**Verdict: accepted for the coordinator's native CI run. No unresolved code or test findings.** The frozen diff is exactly five insertions and eight deletions across the two authorized test files. `real_cli_fixture` alone changes in `tests/test_harness_execute.py`: POSIX uses native symlinks, Windows retains its copied launcher mechanism, and the obsolete macOS dylib block is removed. The file-identity test alone changes in `tests/test_harness_checks.py`, with the exact argument tail and missing-command assertion preserved. Both production files and `tests/test_harness_hooks.py` are byte-identical to the review baseline. Every other function, including the Windows controller, Korean round trip, scope rejection and cancellation assertions, is unchanged.

Independent validation on macOS Python 3.12.11:

```text
uv run --no-sync pytest -o addopts='' -q tests/test_harness_execute.py tests/test_harness_checks.py -k 'real_cli or windows_argv_uses_supplied_path_and_preserves_arguments' --junitxml=.run/remediation-20260925/harness-native-review/affected-cases.xml
```

Result: **7 passed, 0 skipped, 48 deselected**. The reviewer inspected both the log and JUnit cases and rechecked all reviewed file hashes after execution. Evidence: `.run/remediation-20260925/harness-native-review/{affected-cases.log,affected-cases.xml,reviewed-diff.patch,reviewed-digests.json,review-result.json}`. The earlier installed macOS Python 3.10/3.12 startup probes remain supporting evidence; no runtime/dependency installation or shared-environment change occurred.

The reviewer also inspected Sol's `verification.md` and each cited log in `.run/remediation-20260925/harness-native-implementation/`: **60 harness tests passed with zero skips**, Ruff passed, mypy passed for 91 source files, all release versions were aligned at 0.3.0, all 18 envelope kinds passed, and the recorded diff check was clean. No full suite was run for this correction. Sol's report prints a truncated digest for `tests/test_harness_checks.py`; the complete independently computed digests below and in `reviewed-digests.json` identify the accepted files.

| Reviewed file | SHA-256 |
| --- | --- |
| `tests/test_harness_execute.py` | `e39d39a88c26b39296179c9f8803937c34aa2dd7d2f8424688182e9e896d5590` |
| `tests/test_harness_checks.py` | `871a02eaa2aeae99a0af64425fa513f2771bdc3f72fa1e2db8348ab605da9f04` |

Remaining work is root-owned: commit/push if authorized and validate the exact corrected revision through native CI. In particular, Ubuntu 3.10 must reach and pass all six real-CLI cases, and Windows must pass the file-identity assertion while retaining the six already passing real-CLI cases. Local success does not establish a native Linux 3.10 or Windows pass, and existing unrelated native skips must remain separately reported. The reviewer changed only this report and ignored review evidence; no code/test/Git edits were made.
