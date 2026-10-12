from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from opspilot.api.schemas import (
    AnalyticsRead,
    ComparisonRead,
    CopilotRead,
    DatasetRead,
    DatasetVisibilityRequest,
    ExplanationRead,
    HealthRead,
    PreviewRead,
    QueuedRead,
    RulesAppliedRead,
    RulesPreviewRead,
    RunRead,
    ScenarioRead,
    WorkloadPreviewRead,
)
from opspilot.branding import FILE_PREFIX, PRODUCT_DESCRIPTION, PRODUCT_NAME
from opspilot.config import Settings
from opspilot.domain.models import (
    CompareRequest,
    CopilotRequest,
    ExportBundleRequest,
    GenerateRequest,
    Job,
    PlanningInput,
    RunRequest,
    ScenarioRulesRequest,
)
from opspilot.domain.workload_drafts import (
    WorkloadConfirmRequest,
    WorkloadDescriptionRequest,
    WorkloadReviewRequest,
)
from opspilot.persistence.database import create_database
from opspilot.scheduling.milp import solver_available
from opspilot.services.application import ApplicationService
from opspilot.services.data import GENERATOR_VERSION, MAX_CSV_BYTES, generate_data, validate_csv


def require_local_subscription(settings, request):
    if not settings.ai_enabled or settings.ai_provider != "codex_subscription":
        return
    local_hosts = {"127.0.0.1", "::1", "localhost"}
    client_host = request.client.host if request.client else None
    if client_host not in local_hosts or request.url.hostname not in local_hosts:
        raise HTTPException(403, "Subscription AI is available only on this computer.")
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlparse(origin)
            default_port = 443 if request.url.scheme == "https" else 80
            valid = (
                parsed.scheme == request.url.scheme
                and parsed.hostname in local_hosts
                and (parsed.port or default_port) == (request.url.port or default_port)
            )
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(403, "Use the local application to request AI.")


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        engine, sessions = create_database(settings.database_url)
        app.state.service = ApplicationService(sessions, settings)
        app.state.settings = settings
        yield
        app.state.service.close()
        engine.dispose()

    app = FastAPI(
        title=PRODUCT_NAME,
        description=PRODUCT_DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )
    prefix = "/api/v1"

    @app.get(prefix + "/health", response_model=HealthRead)
    def health():
        return {
            "status": "ok",
            "database_available": True,
            "solver_available": solver_available(),
            "ai_available": settings.ai_available,
            "ai_enabled": settings.ai_enabled,
            "ai_provider": settings.ai_provider if settings.ai_enabled else None,
            "ai_model": settings.openai_model if settings.ai_enabled else None,
            "ai_reasoning_effort": "low" if settings.ai_enabled else None,
            "version": "0.1.0",
        }

    @app.get(prefix + "/datasets", response_model=list[DatasetRead])
    def datasets():
        return app.state.service.list_datasets()

    @app.get(prefix + "/datasets/{dataset_id}", response_model=DatasetRead)
    def dataset(dataset_id: str):
        return app.state.service.dataset_detail(dataset_id)

    @app.patch(prefix + "/datasets/{dataset_id}/visibility", response_model=DatasetRead)
    def dataset_visibility(dataset_id: str, request: DatasetVisibilityRequest):
        return app.state.service.set_dataset_visibility(dataset_id, request.is_archived)

    @app.post(prefix + "/datasets/generate", status_code=201, response_model=DatasetRead)
    def generate(request: GenerateRequest):
        if not request.confirmed:
            raise HTTPException(422, "Confirm dataset creation first")
        params = {
            **request.model_dump(exclude={"confirmed", "name"}),
            "generator_version": GENERATOR_VERSION,
        }
        return app.state.service.create_dataset(
            generate_data(request), request.name, "synthetic", params
        )

    @app.post(prefix + "/natural-language/parse", response_model=WorkloadPreviewRead)
    async def describe_workload(request: WorkloadDescriptionRequest, http_request: Request):
        from opspilot.agents.workload_parser import parse_workload
        from opspilot.services.workload_drafts import review_workload

        require_local_subscription(settings, http_request)
        if not settings.ai_available:
            raise HTTPException(
                503,
                "Connect AI to parse a description. CSV and manual generation remain available.",
            )
        try:
            draft = await parse_workload(settings, request.description)
            return review_workload(request.description, draft)
        except Exception as exc:
            raise HTTPException(
                502,
                "The description could not be parsed. Your existing data is unchanged; edit the description or retry.",
            ) from exc

    @app.post(prefix + "/natural-language/review", response_model=WorkloadPreviewRead)
    def review_description(request: WorkloadReviewRequest, http_request: Request):
        from opspilot.services.workload_drafts import review_workload

        require_local_subscription(settings, http_request)
        return review_workload(request.description, request.draft)

    @app.post(prefix + "/natural-language/confirm", status_code=201, response_model=DatasetRead)
    def confirm_description(request: WorkloadConfirmRequest, http_request: Request):
        from opspilot.services.workload_drafts import confirm_workload

        require_local_subscription(settings, http_request)
        return confirm_workload(app.state.service, settings, request)

    async def preview(file, machine_count):
        content = await file.read(MAX_CSV_BYTES + 1)
        return validate_csv(content, machine_count)

    @app.post(prefix + "/datasets/validate-csv", response_model=PreviewRead)
    async def validate(file: UploadFile = File(...), machine_count: int = Form(...)):
        return await preview(file, machine_count)

    @app.post(prefix + "/datasets/import", status_code=201, response_model=DatasetRead)
    async def import_csv(
        file: UploadFile = File(...),
        machine_count: int = Form(...),
        name: str = Form(...),
        confirmed: bool = Form(False),
    ):
        if not confirmed or not 1 <= len(name.strip()) <= 100:
            raise HTTPException(422, "Confirm import with a name between 1 and 100 characters")
        result = await preview(file, machine_count)
        if not result["valid"]:
            raise HTTPException(422, result)
        data = PlanningInput(jobs=[Job(**j) for j in result["jobs"]], machine_count=machine_count)
        return app.state.service.create_dataset(data, name.strip(), "csv")

    @app.get(prefix + "/datasets/{dataset_id}/scenarios", response_model=list[ScenarioRead])
    def scenarios(dataset_id: str):
        return app.state.service.dataset_detail(dataset_id)["scenarios"]

    @app.post(
        prefix + "/datasets/{dataset_id}/scenarios", status_code=201, response_model=ScenarioRead
    )
    def add_machine(dataset_id: str):
        return app.state.service.add_machine(dataset_id)

    @app.get(prefix + "/scenarios/{scenario_id}/runs", response_model=list[RunRead])
    def runs(scenario_id: str):
        return app.state.service.list_runs(scenario_id)

    @app.post(prefix + "/scenarios/{scenario_id}/runs", status_code=202, response_model=QueuedRead)
    def queue_runs(scenario_id: str, request: RunRequest):
        return app.state.service.queue_runs(scenario_id, request)

    @app.get(prefix + "/runs/{run_id}", response_model=RunRead)
    def run(run_id: str):
        return app.state.service.get_run(run_id)

    @app.post(prefix + "/scenarios/{scenario_id}/rules/preview", response_model=RulesPreviewRead)
    def preview_rules(scenario_id: str, request: ScenarioRulesRequest):
        return app.state.service.preview_rules(scenario_id, request)

    @app.post(
        prefix + "/scenarios/{scenario_id}/rules", status_code=202, response_model=RulesAppliedRead
    )
    def apply_rules(scenario_id: str, request: ScenarioRulesRequest):
        return app.state.service.apply_rules(scenario_id, request)

    @app.get(prefix + "/runs/{run_id}/explanation", response_model=ExplanationRead)
    def explanation(run_id: str, baseline_run_id: str | None = None):
        from opspilot.services.explanations import explain_schedule

        return explain_schedule(app.state.service, run_id, baseline_run_id)

    @app.get(prefix + "/runs/{run_id}/late-jobs", response_model=AnalyticsRead)
    def late(run_id: str):
        return app.state.service.analytics(run_id, "late")

    @app.get(prefix + "/runs/{run_id}/machine-utilization", response_model=AnalyticsRead)
    def utilization(run_id: str):
        return app.state.service.analytics(run_id, "utilization")

    @app.post(prefix + "/comparisons", response_model=ComparisonRead)
    def compare(request: CompareRequest):
        return app.state.service.compare(request.run_ids)

    @app.get(prefix + "/runs/{run_id}/exports/{table}.csv")
    def export(run_id: str, table: str):
        content = app.state.service.export(run_id, table)
        return Response(
            content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{FILE_PREFIX}-{table}-{run_id}.csv"'
            },
        )

    @app.post(prefix + "/exports/power-bi")
    def export_bundle(request: ExportBundleRequest):
        from opspilot.services.exports import power_bi_bundle

        content = power_bi_bundle(app.state.service, request.run_ids)
        return Response(
            content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{FILE_PREFIX}-power-bi.zip"'},
        )

    @app.post(prefix + "/copilot/query", response_model=CopilotRead)
    async def copilot(request: CopilotRequest, http_request: Request):
        from opspilot.agents.copilot import answer_query

        require_local_subscription(settings, http_request)
        if not settings.ai_available:
            raise HTTPException(
                503, "AI is disabled. Scheduling, scenarios and exports remain available."
            )
        return await answer_query(app.state.service, settings, request)

    if settings.frontend_dist.is_dir():
        assets = settings.frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "API route not found")
            candidate = (settings.frontend_dist / path).resolve()
            if candidate.is_relative_to(settings.frontend_dist.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(settings.frontend_dist / "index.html")

    return app


app = create_app()
