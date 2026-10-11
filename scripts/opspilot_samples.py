import json
from pathlib import Path

from opspilot.domain.models import GenerateRequest
from opspilot.services.data import GENERATOR_VERSION, generate_data, jobs_csv

directory = Path("data/samples")
directory.mkdir(parents=True, exist_ok=True)
for profile in ["relaxed", "tight", "staggered"]:
    config = GenerateRequest(profile=profile)
    data = generate_data(config)
    (directory / f"{profile}-30-jobs.csv").write_text(jobs_csv(data), encoding="utf-8")
    (directory / f"{profile}-30-jobs.json").write_text(
        json.dumps(
            {
                "parameters": config.model_dump(exclude={"name", "confirmed"}),
                "generator_version": GENERATOR_VERSION,
                "job_hash": data.job_hash,
                "horizon_min": data.horizon_min,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
