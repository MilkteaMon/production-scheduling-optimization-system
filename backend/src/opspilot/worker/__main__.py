import contextlib
import json
import sys


def main():
    payload = json.load(sys.stdin)
    # Native solver discovery can print diagnostics. Stdout is reserved for the protocol.
    with contextlib.redirect_stdout(sys.stderr):
        from opspilot.domain.models import PlanningInput
        from opspilot.scheduling.milp import optimize

        result = optimize(
            PlanningInput.model_validate(payload["data"]), payload["time_limit_seconds"]
        )
    sys.stdout.write(result.model_dump_json())


if __name__ == "__main__":
    main()
