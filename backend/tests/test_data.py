import pytest
from pydantic import ValidationError

from opspilot.domain.models import GenerateRequest, Job
from opspilot.services.data import generate_data, jobs_csv, validate_csv


def test_generator_reproducible_and_csv_roundtrip():
    for profile in ["relaxed", "tight", "staggered"]:
        config = GenerateRequest(profile=profile)
        data = generate_data(config)
        assert data == generate_data(config)
        preview = validate_csv(b"\xef\xbb\xbf" + jobs_csv(data).encode(), 4)
        assert preview["valid"]
        assert preview["total_jobs"] == 30


@pytest.mark.parametrize(
    "row",
    ["A,1.5,0,5,1", "A,nan,0,5,1", "A,0,0,5,1", "A,2,-1,5,1", "A,2,0,5,11", "A,2,0,5,1,extra"],
)
def test_invalid_csv(row):
    content = (
        "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n" + row
    ).encode()
    assert not validate_csv(content, 3)["valid"]


def test_duplicate_and_late_release():
    header = "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n"
    assert not validate_csv((header + "A,2,0,1,1\nA,2,0,1,1").encode(), 3)["valid"]
    preview = validate_csv((header + "A,2,10,1,1").encode(), 3)
    assert preview["valid"] and preview["warnings"]
    with pytest.raises(ValidationError):
        Job(
            job_id="A",
            processing_time_min=2.0,
            release_time_min=0,
            due_time_min=3,
            priority_weight=1,
        )


@pytest.mark.parametrize(
    "content,machines",
    [
        (b"x" * (1024 * 1024 + 1), 1),
        (b"\xff\xfe", 1),
        (b"job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n", 1),
        (b"job_id,job_id,release_time_min,due_time_min,priority_weight\nA,2,0,5,1", 1),
        (b"job_id,processing_time_min,release_time_min,due_time_min,priority_weight\nA,2,0,5", 1),
        (
            (
                "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\nA,"
                + "9" * 5000
                + ",0,5,1"
            ).encode(),
            1,
        ),
        (
            (
                "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n"
                + "\n".join(f"J{i},2,0,5,1" for i in range(51))
            ).encode(),
            1,
        ),
        (b"job_id,processing_time_min,release_time_min,due_time_min,priority_weight\nA,2,0,5,1", 0),
    ],
    ids=[
        "too-large",
        "non-utf8",
        "empty",
        "duplicate-columns",
        "missing-field",
        "extreme-integer",
        "too-many-jobs",
        "invalid-machines",
    ],
)
def test_import_boundaries_are_validation_errors(content, machines):
    result = validate_csv(content, machines)
    assert not result["valid"] and result["errors"]
    assert all("field" in error and "row" in error for error in result["errors"])
