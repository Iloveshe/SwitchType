from __future__ import annotations

import argparse
import json

try:
    from command_safety import (
        command_is_executable,
        command_mutates_state,
        command_records_audio,
        command_requests_mac_permissions,
        command_requires_user_approval,
        format_command_approval,
        format_command_safety,
    )
except ModuleNotFoundError:
    from bench.scripts.command_safety import (
        command_is_executable,
        command_mutates_state,
        command_records_audio,
        command_requests_mac_permissions,
        command_requires_user_approval,
        format_command_approval,
        format_command_safety,
    )


CAPTURE_ONCE_COMMAND = "DURATION=5 make doubao-shadow-capture-once-packaged"
PLAN_COMMAND = "make doubao-shadow-capture-once-packaged-plan-json"
CAPTURE_ONCE_STEPS = [
    {
        "command": "make doubao-shadow-status-json",
        "description": "Read current recorder status before fixed-duration capture.",
        "approval_reason": "read-only recorder status check",
        "mutates_state": False,
        "requests_mac_permissions": False,
        "records_audio": False,
    },
    {
        "command": "DURATION=5 make doubao-shadow-record-seconds-auto-packaged",
        "description": "Record one fixed-duration packaged shadow clip with focused-text capture enabled.",
        "approval_reason": "records local microphone audio for a fixed-duration capture",
        "mutates_state": True,
        "requests_mac_permissions": False,
        "records_audio": True,
    },
    {
        "command": "make doubao-shadow-latest-preview",
        "description": "If a new clip was written, print a local ASR preview for that newest clip.",
        "approval_reason": "may build the local ASR preview helper before printing a preview",
        "mutates_state": True,
        "requests_mac_permissions": False,
        "records_audio": False,
    },
    {
        "command": "make doubao-shadow-status",
        "description": "Print shadow recorder status after the attempt.",
        "approval_reason": "read-only recorder status check",
        "mutates_state": False,
        "requests_mac_permissions": False,
        "records_audio": False,
    },
]


def command_payload(command: str) -> dict[str, object]:
    return {
        "command": command,
        "is_executable_command": command_is_executable(command),
        "requires_user_approval": command_requires_user_approval(command),
        "mutates_state": command_mutates_state(command),
        "requests_mac_permissions": command_requests_mac_permissions(command),
        "records_audio": command_records_audio(command),
    }


def build_approval_summary(steps: list[dict[str, object]]) -> dict[str, object]:
    steps_requiring_user_approval = [
        {
            "index": step["index"],
            "command": step["command"],
            "approval_reason": step["approval_reason"],
        }
        for step in steps
        if step.get("requires_user_approval")
    ]
    return {
        "requires_user_approval": bool(steps_requiring_user_approval),
        "approval_step_count": len(steps_requiring_user_approval),
        "steps_requiring_user_approval": steps_requiring_user_approval,
        "mutating_step_indices": [step["index"] for step in steps if step.get("mutates_state")],
        "permission_prompt_step_indices": [
            step["index"] for step in steps if step.get("requests_mac_permissions")
        ],
        "recording_step_indices": [step["index"] for step in steps if step.get("records_audio")],
    }


def build_capture_once_plan() -> dict[str, object]:
    steps = []
    for index, step_spec in enumerate(CAPTURE_ONCE_STEPS, start=1):
        command = str(step_spec["command"])
        step = command_payload(command)
        step["index"] = index
        step["description"] = step_spec["description"]
        step["approval_reason"] = step_spec["approval_reason"]
        step["mutates_state"] = step_spec["mutates_state"]
        step["requests_mac_permissions"] = step_spec["requests_mac_permissions"]
        step["records_audio"] = step_spec["records_audio"]
        steps.append(step)

    return {
        "command": CAPTURE_ONCE_COMMAND,
        "command_is_executable": command_is_executable(CAPTURE_ONCE_COMMAND),
        "command_requires_user_approval": command_requires_user_approval(CAPTURE_ONCE_COMMAND),
        "command_mutates_state": command_mutates_state(CAPTURE_ONCE_COMMAND),
        "command_requests_mac_permissions": command_requests_mac_permissions(CAPTURE_ONCE_COMMAND),
        "command_records_audio": command_records_audio(CAPTURE_ONCE_COMMAND),
        "plan_command": PLAN_COMMAND,
        "plan_is_executable": command_is_executable(PLAN_COMMAND),
        "plan_requires_user_approval": command_requires_user_approval(PLAN_COMMAND),
        "plan_mutates_state": command_mutates_state(PLAN_COMMAND),
        "plan_requests_mac_permissions": command_requests_mac_permissions(PLAN_COMMAND),
        "plan_records_audio": command_records_audio(PLAN_COMMAND),
        "does_not_execute": True,
        "records_audio": False,
        "requests_mac_permissions": False,
        "mutates_state": False,
        "writes_shadow_audio": False,
        "starts_capture": False,
        "approval_summary": build_approval_summary(steps),
        "steps": steps,
    }


def _format_step_indices(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ",".join(str(item) for item in value)


def format_approval_summary(summary: dict[str, object]) -> str:
    return (
        f"approval_steps={summary.get('approval_step_count', 0)}, "
        f"mutating_steps={_format_step_indices(summary.get('mutating_step_indices'))}, "
        f"permission_prompt_steps={_format_step_indices(summary.get('permission_prompt_step_indices'))}, "
        f"recording_steps={_format_step_indices(summary.get('recording_step_indices'))}"
    )


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def _step_safety(step: dict[str, object]) -> str:
    return (
        f"safety: mutates_state={_yes_no(step.get('mutates_state'))}, "
        f"requests_mac_permissions={_yes_no(step.get('requests_mac_permissions'))}, "
        f"records_audio={_yes_no(step.get('records_audio'))}"
    )


def print_human_capture_once_plan(plan: dict[str, object]) -> None:
    command = str(plan.get("command") or "")
    print(f"Plan: {command} will run:")
    print(format_command_approval("Plan command", str(plan.get("plan_command") or "")))
    print(
        format_command_safety(
            "Plan command",
            mutates_state=plan.get("plan_mutates_state"),
            requests_mac_permissions=plan.get("plan_requests_mac_permissions"),
            records_audio=plan.get("plan_records_audio"),
        )
    )
    print(format_command_approval("Target command", command))
    print(
        format_command_safety(
            "Target command",
            mutates_state=plan.get("command_mutates_state"),
            requests_mac_permissions=plan.get("command_requests_mac_permissions"),
            records_audio=plan.get("command_records_audio"),
        )
    )
    summary = plan.get("approval_summary")
    if isinstance(summary, dict):
        print(f"Approval summary: {format_approval_summary(summary)}")
    steps = plan.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            print(f"{step.get('index', '?')}. {step.get('command', '')}")
            description = str(step.get("description") or "").strip()
            if description:
                print(f"   description: {description}")
            print(f"   approval: {'user approval required' if step.get('requires_user_approval') else 'no approval needed'}")
            print(f"   {_step_safety(step)}")
            approval_reason = str(step.get("approval_reason") or "").strip()
            if approval_reason:
                print(f"   approval_reason: {approval_reason}")
    print("This plan target does not record, write files, run ASR, request permissions, or start capture.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human", action="store_true", help="print a readable non-executing plan")
    args = parser.parse_args()
    plan = build_capture_once_plan()
    if args.human:
        print_human_capture_once_plan(plan)
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
