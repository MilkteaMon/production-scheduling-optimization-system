# Create a workload from natural language

Choose **Describe workload** in the page toolbar. Describe orders and identical machines in
Chinese or English, then choose **Interpret description**. This uses the connected AI account
and keeps the explicitly configured model; this owner's local setup uses GPT-6.1 Sol with low
reasoning effort through the ChatGPT/Codex subscription. A single interpretation makes one
structured model request. It has no business, shell, file or app tools.

Example:

> 我有两台相同的机器。订单 A 加工需要 40 分钟，90 分钟内交付；订单 B 需要 20 分钟，
> 60 分钟内交付。两个订单现在都可以开工，A 必须准时完成。

The result is an editable draft, not a saved workload or schedule. Review the machine count,
each processing duration, available time, due time, priority weight and hard on-time flag.
After editing the table, choose **Check edited draft** to run local validation again.
Approve the review checkbox, name the workload, then choose **Confirm and create plan**.
Only confirmation saves a new workload and queues FCFS, EDD and MILP with the selected budget.
Original workloads and their jobs remain unchanged. The new workload is selected in the Web UI.

## Try a conversational description

You can paste ordinary spoken language; it need not be a formal specification:

> 我这边有三台一样的机器，先排四个单。A 做四十分钟，七十分钟内必须完成，
> 优先级八。B 做五十五分钟，九十分钟内交，优先级六。C 二十分钟后才能开始，
> 做二十五分钟，六十分钟内必须完成，优先级十。D 做一个小时十分钟，
> 一百分钟内交，优先级三。时间都从现在算，没说要等的就能马上开。
> A 和 C 不能迟，其他的尽量少迟。

Check that the draft shows three identical machines, four jobs, D's processing time as 70
minutes, and hard deadlines only for A and C. Due times for B and D remain soft targets.
This example illustrates extraction; it does not assert an optimal scheduling result.

If you say only “有两台机器，A 做四十分钟，B 做二十分钟”, the application should ask
for the missing due times. Enter them in the table or supply an additional description.
After confirmation, use the separate Copilot or **Plan commitments / What-if** controls to
inspect late orders, propose an extra machine and compare saved results. The description
entry itself is a workload-creation flow, not an unrestricted multi-turn planning assistant.

The entry currently accepts text. Operating-system voice typing can fill the text field;
there is no built-in microphone, speech transcription service or reinforcement-learning model.

## Missing information and defaults

- Missing machine counts, processing times or due times stay null and block confirmation.
- The application lists questions. Supply values directly in the editable table, or add a
  supplement in natural language and choose **Add details and re-interpret**.
- Unstated available times use 0 and unstated priorities use equal weight 1. These defaults
  are visibly listed for approval. They are never represented as facts extracted from the text.
- Non-ASCII source names remain visible in the draft. If an ASCII job ID is absent, the review
  suggests a collision-free ID and lists the mapping before confirmation.
- Priority descriptions such as high/low need an explicit numeric mapping when ambiguous.
- Hard deadlines are selected only for explicitly required on-time orders. Other due times
  remain soft targets. Infeasible hard commitments can be confirmed as experiments, but the
  solver reports infeasibility and no valid result rather than inventing metrics.

Supported scope is 1–5 identical machines, 1–50 single-operation jobs, whole-minute processing
and times from a common planning start, weights 1–10, and optional hard deadlines. Explicit hour
durations can be converted exactly into whole minutes. Calendar/clock deadlines need a resolved
time origin. Different machine capabilities, multi-operation routing, precedence, changeovers,
calendars and breakdowns are outside this scheduling model and block confirmation when detected.
Model extraction can make mistakes; the review table and final approval remain necessary.

## API and persistence

- `POST /api/v1/natural-language/parse`: one bounded extraction, then deterministic review;
  no application records or runs are created.
- `POST /api/v1/natural-language/review`: validate an edited draft locally, without an AI call.
- `POST /api/v1/natural-language/confirm`: require `confirmed=true`, a confirmation UUID,
  a nonempty workload name and a complete valid draft. Recheck all fields before saving.

Confirmation records the original description, approved draft and displayed defaults in the
dataset metadata. The scenario persists its hard-deadline IDs. Retry with the same confirmation
UUID and unchanged data returns the original workload; changed data with a used UUID is rejected.
The single-process application lock protects this operation, and a full scheduling queue is
rejected before creation. This is a local single-user application, not a multi-worker service.
No database schema migration is needed for this feature.

AI stays optional for existing workflows. The local subscription provider retains its localhost,
Host and Origin checks on these endpoints. Credential files are never read or copied by the app;
the official Codex CLI handles its own login. Parser failures do not alter existing data.
The implementation uses [structured model output](https://developers.openai.com/api/docs/guides/structured-outputs)
and the official CLI's [output schema option](https://learn.chatgpt.com/docs/cli/reference).

## Verification

Offline tests cover missing values, invalid partial drafts, defaults, suggested IDs, unsupported
requirements, confirmation, queue pressure, retry safety and preservation of hard commitments.
Desktop/mobile browser tests cover table edits, follow-up descriptions, approval, actual local
scheduling, accessibility and responsive layout. Browser model responses are mocked.

On 13 October 2026 (Singapore), two real GPT-6.1 Sol/low subscription interpretations verified
the Chinese missing-deadline example and its supplement. Before confirmation there were no new
datasets or runs. A confirmed two-order/two-machine demonstration then produced a validated,
solver-proven zero-weighted-tardiness result and retained A's hard deadline. Repeating the same
confirmation created no duplicates. This is a functional smoke test, not a broad evaluation of
language extraction quality. See [the saved verification receipt](natural-language-checks.json)
for the executed checks. Receipts describe their recorded verification time, not live account
status; the earlier planning and subscription receipts precede this workload-entry implementation.
