#!/usr/bin/env python3
"""Run and report a small paired Pi skill-effectiveness pilot.

The runner deliberately evaluates a fixed, small scenario set rather than acting as a
repository-wide benchmark framework. Every run starts from a copied fixture and the
only control/treatment difference is whether the target skill is explicitly loaded.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = ROOT / "docs" / "evaluations" / "skill-effectiveness-pilot-runs"
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "skill-pilot" / "scenarios.json"


@dataclass(frozen=True)
class Scenario:
    identifier: str
    skill: str
    split: str
    fixture: Path
    prompt: str
    all_of: tuple[str, ...]
    any_of: tuple[tuple[str, ...], ...]


def load_scenarios(path: Path = SCENARIO_PATH) -> list[Scenario]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = []
    for item in data["scenarios"]:
        grader = item["grader"]
        scenarios.append(
            Scenario(
                identifier=item["id"],
                skill=item["skill"],
                split=item["split"],
                fixture=path.parent / item["fixture"],
                prompt=item["prompt"],
                all_of=tuple(grader["all_of"]),
                any_of=tuple(tuple(group) for group in grader["any_of"]),
            )
        )
    return scenarios


def grade_output(output: str, exit_code: int, scenario: Scenario) -> dict[str, Any]:
    """Grade a run without ever converting a failed execution into a pass."""
    if exit_code != 0:
        return {"status": "invalid", "reason": f"Pi exited {exit_code}", "checks": []}
    if not output.strip():
        return {"status": "invalid", "reason": "Pi produced no output", "checks": []}

    normalized = output.casefold()
    checks = []
    for term in scenario.all_of:
        checks.append({"kind": "all_of", "terms": [term], "passed": term.casefold() in normalized})
    for terms in scenario.any_of:
        checks.append(
            {
                "kind": "any_of",
                "terms": list(terms),
                "passed": any(term.casefold() in normalized for term in terms),
            }
        )

    missing = [check["terms"] for check in checks if not check["passed"]]
    if missing:
        return {"status": "failed", "reason": "Missing required evidence", "checks": checks}
    return {"status": "passed", "reason": "All deterministic checks passed", "checks": checks}


def pi_command(
    scenario: Scenario,
    condition: str,
    model: str,
    workspace: Path,
) -> list[str]:
    command = [
        "pi",
        "--print",
        "--no-session",
        "--no-context-files",
        "--no-extensions",
        "--no-skills",
        "--approve",
        "--tools",
        "read,bash,grep,find",
        "--model",
        model,
    ]
    if condition == "with_skill":
        command.extend(["--skill", str((ROOT / scenario.skill).resolve())])
    command.append(scenario.prompt)
    return command


def run_cell(
    scenario: Scenario,
    condition: str,
    repetition: int,
    model: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"skill-pilot-{scenario.identifier}-") as temporary:
        workspace = Path(temporary) / "workspace"
        shutil.copytree(scenario.fixture, workspace)
        command = pi_command(scenario, condition, model, workspace)
        started = datetime.now(UTC)
        began = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
                timeout=300,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            result = subprocess.CompletedProcess(command, 124, stdout, stderr)
        duration_seconds = round(time.monotonic() - began, 3)

    grader = grade_output(result.stdout, result.returncode, scenario)
    return {
        "schema_version": 1,
        "scenario": scenario.identifier,
        "split": scenario.split,
        "skill": scenario.skill,
        "condition": condition,
        "repetition": repetition,
        "started_at": started.isoformat(),
        "duration_seconds": duration_seconds,
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "grader": grader,
    }


def save_result(results_dir: Path, result: dict[str, Any]) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{result['scenario']}--{result['condition']}--{result['repetition']}.json"
    target = results_dir / filename
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_results(results_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(results_dir.glob("*.json"))]


def report_markdown(results: list[dict[str, Any]]) -> str:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for result in results:
        grouped[result["scenario"]][result["condition"]].append(result)

    lines = [
        "# Automated skill-effectiveness pilot results",
        "",
        "This is a directional paired pilot, not a universal quality threshold. Each result file",
        "contains the raw model output, command, timing, and deterministic grader checks. Literal",
        "text checks are mechanical diagnostics; interpret them only alongside the blinded review.",
        "",
        "| Scenario | Split | Skill | Baseline | With skill | Invalid | Interpretation |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for scenario, conditions in sorted(grouped.items()):
        baseline = conditions["baseline"]
        treatment = conditions["with_skill"]
        all_runs = baseline + treatment
        passed = {
            name: sum(run["grader"]["status"] == "passed" for run in runs)
            for name, runs in (("baseline", baseline), ("with_skill", treatment))
        }
        invalid = sum(run["grader"]["status"] == "invalid" for run in all_runs)
        split = all_runs[0]["split"] if all_runs else "unknown"
        skill = all_runs[0]["skill"] if all_runs else "unknown"
        if invalid:
            interpretation = "invalid runs present; do not compare aggregate scores"
        elif passed["baseline"] == passed["with_skill"]:
            interpretation = "equal literal-check outcomes; no benefit claim"
        elif passed["with_skill"] > passed["baseline"]:
            interpretation = "literal-check treatment delta; inspect blind review"
        else:
            interpretation = "literal-check regression; inspect blind review"
        lines.append(
            f"| {scenario} | {split} | {skill} | {passed['baseline']}/{len(baseline)} "
            f"| {passed['with_skill']}/{len(treatment)} | {invalid} | {interpretation} |"
        )

    statuses = Counter(result["grader"]["status"] for result in results)
    lines.extend(
        [
            "",
            "## Validity notes",
            "",
            f"- Raw run statuses: {dict(sorted(statuses.items()))}.",
            "- A grader failure, empty output, timeout, or non-zero Pi exit is `invalid`, never a pass.",
            "- Equal outcomes are reported as non-discriminating rather than evidence that either arm is better.",
            "- Calibration scenarios are for fixture/grader checks; hold-out scenarios are the evidence used for the maintain/no-maintain decision.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    if args.report_only:
        Path(args.report).write_text(
            report_markdown(load_results(Path(args.results_dir))), encoding="utf-8"
        )
        return 0

    scenarios = load_scenarios(Path(args.scenarios))
    if args.dry_run:
        for scenario in scenarios:
            for condition in ("baseline", "with_skill"):
                print(" ".join(pi_command(scenario, condition, args.model or "MODEL_REQUIRED", Path("."))))
        return 0
    if not args.model:
        raise SystemExit("--model is required for real runs so the evaluation records a pinned route")

    selected = [scenario for scenario in scenarios if not args.scenario or scenario.identifier in args.scenario]
    for scenario in selected:
        for repetition in range(1, args.repetitions + 1):
            for condition in ("baseline", "with_skill"):
                result = run_cell(scenario, condition, repetition, args.model)
                saved = save_result(Path(args.results_dir), result)
                print(f"{result['scenario']} {condition} #{repetition}: {result['grader']['status']} ({saved})")

    results = load_results(Path(args.results_dir))
    Path(args.report).write_text(report_markdown(results), encoding="utf-8")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Pinned Pi model, for example openai-codex/gpt-5.6-luna")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--scenario", action="append", help="Run only this scenario ID (repeatable)")
    parser.add_argument("--scenarios", default=SCENARIO_PATH)
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--report",
        default=ROOT / "docs" / "evaluations" / "skill-effectiveness-pilot-results.md",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", action="store_true", help="Regenerate the report from saved raw records")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
