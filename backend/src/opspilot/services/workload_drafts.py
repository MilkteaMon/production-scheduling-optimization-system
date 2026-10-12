import hashlib
import json
import re

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from opspilot.domain.models import Job, PlanningInput, RunRequest
from opspilot.persistence.models import Dataset


def review_workload(description, draft):
    chinese = bool(re.search(r"[\u4e00-\u9fff]", description))

    def choose(zh, en):
        return zh if chinese else en

    questions, errors, assumptions, jobs = [], [], [], []
    if draft.machine_count is None:
        questions.append(
            choose("有几台相同的机器？请填入 1–5。", "How many identical machines (1–5)?")
        )
    elif not 1 <= draft.machine_count <= 5:
        errors.append(choose("机器数量必须为 1–5。", "Machine count must be between 1 and 5."))
    if not draft.jobs:
        questions.append(choose("请至少描述一个订单。", "Describe at least one order."))
    if draft.time_basis != "minutes_from_start":
        questions.append(
            choose(
                "请把时间换成从同一个排程起点算起的分钟数。",
                "Resolve all times to whole minutes from one common planning start.",
            )
        )
    reserved = {j.job_id for j in draft.jobs if j.job_id}
    seen = set()
    releases, priorities = [], []
    names = {
        "processing_time_min": choose("加工时间", "processing time"),
        "release_time_min": choose("可开工时间", "release time"),
        "due_time_min": choose("交期", "due time"),
        "priority_weight": choose("优先级权重", "priority weight"),
        "job_id": choose("订单编号", "job ID"),
    }
    for index, row in enumerate(draft.jobs):
        identifier = row.job_id
        if not identifier:
            number = index + 1
            while f"JOB-{number:03}" in reserved | seen:
                number += 1
            identifier = f"JOB-{number:03}"
            assumptions.append(
                choose(
                    f"{row.label or '订单'}：建议编号 {identifier}。",
                    f"{row.label or 'Order'}: suggested ID {identifier}.",
                )
            )
        if identifier in seen:
            errors.append(choose(f"编号重复：{identifier}。", f"Duplicate job ID: {identifier}."))
        seen.add(identifier)
        missing = False
        for field in ("processing_time_min", "due_time_min"):
            if getattr(row, field) is None:
                questions.append(
                    choose(
                        f"{identifier} 的{names[field]}是多少分钟？",
                        f"What is {identifier}'s {names[field]} in minutes?",
                    )
                )
                missing = True
        release = row.release_time_min
        weight = row.priority_weight
        if release is None:
            release = 0
            releases.append(identifier)
        if weight is None:
            weight = 1
            priorities.append(identifier)
        # Validate every supplied value, including partially completed rows.
        candidate = {
            "job_id": identifier,
            "processing_time_min": row.processing_time_min
            if row.processing_time_min is not None
            else 1,
            "release_time_min": release,
            "due_time_min": row.due_time_min if row.due_time_min is not None else 0,
            "priority_weight": weight,
        }
        try:
            job = Job(**candidate)
            if not missing:
                jobs.append(job)
        except ValidationError as exc:
            errors.extend(
                f"{identifier} · {names.get(str(e['loc'][0]), str(e['loc'][0]))}: {e['msg']}"
                for e in exc.errors()
            )
    if releases:
        assumptions.append(
            choose(
                f"未提供可开工时间的订单按 0 分钟处理：{', '.join(releases)}。",
                f"Release defaults to 0 minutes where unstated: {', '.join(releases)}.",
            )
        )
    if priorities:
        assumptions.append(
            choose(
                f"未提供权重的订单按相同权重 1 处理：{', '.join(priorities)}。",
                f"Unstated priorities use equal weight 1: {', '.join(priorities)}.",
            )
        )
    questions.extend(draft.clarifications)
    ready = not questions and not errors and not draft.unsupported_requirements
    plan = None
    warnings = []
    if ready:
        ids = [
            jobs[index].job_id for index, row in enumerate(draft.jobs) if row.must_finish_on_time
        ]
        plan = PlanningInput(jobs=jobs, machine_count=draft.machine_count, must_finish_job_ids=ids)
        for job in jobs:
            if job.release_time_min + job.processing_time_min > job.due_time_min:
                hard = job.job_id in ids
                warnings.append(
                    choose(
                        f"{job.job_id} 最早完工时间超过交期"
                        + ("，准时完成要求不可行。" if hard else "，会产生延误。"),
                        f"{job.job_id}: earliest completion exceeds its due time"
                        + (
                            "; its hard deadline is infeasible."
                            if hard
                            else "; tardiness is unavoidable."
                        ),
                    )
                )
    return {
        "draft": draft.model_dump(),
        "ready": ready,
        "questions": questions,
        "errors": errors,
        "assumptions": assumptions,
        "unsupported_requirements": draft.unsupported_requirements,
        "warnings": warnings,
        "planning_input": plan.model_dump() if plan else None,
    }


def confirm_workload(service, settings, request):
    if not request.confirmed:
        raise HTTPException(422, "Review and confirm the workload first")
    preview = review_workload(request.description, request.draft)
    if not preview["ready"]:
        raise HTTPException(422, preview)
    if not request.name.strip():
        raise HTTPException(422, "Give the workload a name")
    data = PlanningInput.model_validate(preview["planning_input"])
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "input_hash": data.input_hash,
                "name": request.name.strip(),
                "description": request.description,
                "budget": request.time_limit_seconds,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    key = str(request.confirmation_id)
    with service.lock:
        with service.sessions() as session:
            records = session.scalars(
                select(Dataset).where(Dataset.source_kind == "natural_language")
            ).all()
            for record in records:
                if (record.generator_params or {}).get("confirmation_id") == key:
                    if record.generator_params.get("confirmation_hash") != fingerprint:
                        raise HTTPException(
                            409, "This confirmation already created a different workload"
                        )
                    return service.dataset_detail(record.id, session)
        return service.create_dataset(
            data,
            request.name.strip(),
            "natural_language",
            {
                "description": request.description,
                "confirmed_draft": request.draft.model_dump(),
                "review_assumptions": preview["assumptions"],
                "confirmation_id": key,
                "confirmation_hash": fingerprint,
                "parser_version": "1.0",
                "configured_model": settings.openai_model,
            },
            initial_run_request=RunRequest(
                methods=["fcfs", "edd", "milp"], time_limit_seconds=request.time_limit_seconds
            ),
        )
