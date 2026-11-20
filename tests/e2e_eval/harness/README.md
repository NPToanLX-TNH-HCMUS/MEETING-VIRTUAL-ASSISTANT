# E2E evaluation harness

Runs the scenarios in `../scenarios/` through the backend and scores the outputs against the ground truth.

| File | Role |
|---|---|
| `run.py` | Runs scenarios through the FastAPI app in-process, then calls `score.py` |
| `score.py` | Scores a run folder; writes `score.json` per scenario, `results.csv` and `report.md` |
| `evaluate.py` | Metrics of one scenario (TR, MN, AG, SY) and item matching |
| `checks.py` | One function per check type of `expected_behavior.json` |
| `metrics.py` | Edit distance, WER / CER, entity recall, matcher, P / R / F1 |
| `textnorm.py` | Text normalisation (ANNOTATION_GUIDE.md, section 1) |
| `data.py` | Loads scenarios, ground truth and run outputs |
| `selftest.py` | Checks the scorer: perfect outputs score perfectly, planted mistakes are caught |
| `validate.py` | Checks the dataset: audio length and SHA-256, transcript format, quotes, ids, aliases, key entities, agenda spans, check parameters |

## Usage

From the repository root, with the project environment and a `.env` holding `ELEVENLABS_API_KEY`, `GROQ_API_KEY` and `OPENROUTER_API_KEY`:

```
python tests/e2e_eval/harness/run.py --scenarios S13            # cheapest first run (silence)
python tests/e2e_eval/harness/run.py --scenarios S01 S02 --name baseline
python tests/e2e_eval/harness/run.py --all --name baseline
python tests/e2e_eval/harness/run.py --scenarios S04 S07 --name baseline   # run some again; the report covers all
python tests/e2e_eval/harness/score.py --run tests/e2e_eval/runs/baseline   # score again, no API calls
python tests/e2e_eval/harness/run.py --scenarios S10 --app-root ../mva-fix --name fix_s10   # test a fix branch checked out elsewhere
```

S11 needs its generated documents first: `python tests/e2e_eval/scripts/make_s11_files.py`.

Results go to `tests/e2e_eval/runs/<name>/` (ignored by git). If one scenario crashes, its traceback is saved in `<SID>/error.txt` and the run goes on with the next scenario.

After changing the ground truth or the harness, run both checks (no backend, no API key):

```
python tests/e2e_eval/harness/validate.py      # the dataset is consistent
python tests/e2e_eval/harness/selftest.py      # the scorer still scores correctly
```

## What is real and what is replaced

- Replaced: the microphone (the recorder copies the scenario's `meeting.wav` to the meeting folder; for S12, only the parts outside the pauses) and the clock (frozen at the scenario's `meeting_date`, so relative deadlines resolve as in the ground truth).
- Observed, not changed: every LLM request and its answer are logged to `llm_calls.jsonl`.
- Simulated faults (S11, S12): calls in the wrong order, and missing API keys for one call.
- Real: every API route, speech-to-text, LLM calls and file storage. These use the services' quota.
- Rate limits: when every LLM attempt of a step fails with HTTP 429, the harness waits (60, 90, 120 s) and calls the step again; the rate-limited calls are logged as `rate_limited:<step>` and ignored by the checks.
- Not run: the live path (WebSocket transcript, pause / resume, live agenda tracking). Its checks are reported as `not_implemented`.

## Scoring outputs produced by hand

`score.py` only reads files, so outputs saved from the UI can be scored too: create `runs/<name>/<SID>/` with `transcript.txt` and `minutes.json` (the JSON of `GET /api/v1/meetings/{id}/minutes`), optionally `agenda_proposal.json` and `agenda.json`. Checks without data are reported as `skipped`.

## Matching

System items are matched to ground-truth items one-to-one, highest similarity first, above a threshold τ.
The default matcher is lexical (shared content words, τ = 0.35). `--matcher embed --embed-url <EMBED_URL>` uses the team's embedding server.
When the matcher pairs items wrongly, write the decision in `ground_truth/adjudication.json`:

```json
{"action_items": [{"gt": "AI2", "system": "exact system task text", "match": true}]}
```

Sections: `action_items`, `decisions`, `unresolved_issues`, `agenda`.
