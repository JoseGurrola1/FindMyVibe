# FindMyVibe
An AI-powered, Akinator-style discovery game that finds places matching your vibe through adaptive questions, real-world search, and feedback.

## Gemini next-question milestone

`gemini_questions.py` generates **one** next question from session data. It does
not run a game loop, change session state, search for places, or integrate a UI.
The existing `places.py` SerpApi script is independent and unchanged.

### Relationship to the application

The application already uses `gemini_ai.ask_question` through `main.py` and
`/api/game/next`. This milestone is a standalone example with overlapping question
generation functionality; it does not replace or connect to that application path.
It accepts explicit location and active preferences, returns `target_attribute`,
and enforces stricter output validation. Its session format differs from the
application's history/rejection-feedback format, and it does not handle rejection
feedback. It uses `gemini-flash-latest` rather than the application's
`gemini-3.5-flash-lite`. Consolidating these implementations requires a separate
integration decision. `gemini_ai.py`, `main.py`, `requirements.txt`, and the frontend
are unchanged by this milestone; `requirements-gemini.txt` is for this example.

### Setup and example

Use Python 3.10+ (verified with Python 3.12). From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-gemini.txt
```

Create a Gemini Developer API key in [Google AI Studio](https://aistudio.google.com/apikey).
Set `GEMINI_API_KEY` in your **server process environment**, using your deployment's
secret manager or secure environment settings. For a local Bash session, you can
enter it without echoing it or storing the value in shell history:

```sh
read -r -s -p 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
.venv/bin/python example_question.py
unset GEMINI_API_KEY
```

The example loads `.env` from the folder containing `example_question.py`, using
`python-dotenv` with `override=False`. Existing process environment values take
precedence, regardless of the terminal's working directory. The Gemini module
itself still reads only the process environment. `.env` is already ignored by Git;
never commit the key or send it to a browser.

For Windows PowerShell, with your existing `.env` in the FindMyVibe project folder
containing `GEMINI_API_KEY`, run the following. Replace the first path with your
actual checkout location. No virtual environment activation is required:

```powershell
Set-Location "C:\path\to\FindMyVibe"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-gemini.txt
git check-ignore -- .env
.\.venv\Scripts\python.exe .\example_question.py
```

`git check-ignore` should print `.env`, not its contents. If PowerShell already has
`GEMINI_API_KEY` set, that value wins over `.env`; to intentionally use the file's
value instead, remove the process value before running the example:

```powershell
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe .\example_question.py
```

Allow outbound HTTPS to `generativelanguage.googleapis.com`.
The example sends sample Austin session data to Gemini and consumes API quota.
It prints validated JSON to stdout, or a concise error to stderr with exit code 1.

### Module interface

```python
from gemini_questions import SessionData, generate_next_question

session = SessionData(
    location="Austin, TX",
    active_preferences={"setting": "outdoors", "budget": "low cost"},
    previous_questions=["Would you prefer to be indoors or outdoors?"],
    answers=["Outdoors"],
)
question = generate_next_question(session)
print(question.model_dump())  # JSON-compatible dict
```

Preferences map attribute names to string values. Questions and answers are ordered
lists paired by position; both may be empty. Invalid inputs raise Pydantic
`ValidationError` when creating `SessionData`.

The returned `NextQuestion` contains exactly these fields (illustrative output):

```json
{
  "question": "What atmosphere would you prefer?",
  "options": ["Quiet and relaxed", "Lively and social", "Somewhere in between"],
  "target_attribute": "atmosphere"
}
```

Gemini receives a JSON Schema through `response_json_schema` with
`response_mime_type="application/json"`. Local validation also rejects missing or
extra fields, empty strings, wrong types, options outside the 2–4 range, duplicate
options (ignoring case and surrounding whitespace), and exact repeated questions
(ignoring case and surrounding whitespace). The prompt asks for one unresolved
preference; semantic relevance and paraphrased repetition are not guaranteed by
schema validation. `target_attribute` is a nonempty string rather than a fixed
game-wide attribute taxonomy for this milestone.

The default model is the official SDK documentation's `gemini-flash-latest` alias.
Its backing model may change; pass `model="your-supported-model-id"` to select
another model supporting structured output.

Failures raise `QuestionGenerationError` subclasses:

- `MissingCredentialsError`: absent or blank `GEMINI_API_KEY`; no API call occurs.
- `GeminiAPIError`: API rejection (including auth/quota) or network/timeout failure.
- `InvalidResponseError`: empty/blocked response, malformed JSON, invalid fields,
  or an exactly repeated question.

Calls use a 30-second HTTP timeout and one SDK attempt. No automatic fallback
question, game-state mutation, or application retry loop is included. Service
error bodies and credentials are not included in the module's error messages.

### Verification

```sh
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
```

Tests use mocked Gemini calls and real SDK response objects to exercise request
construction, session serialization, validation, and error handling without keys
or network access. They do not establish live model behavior. Run the example
with a valid key and network access to check a live response.

### Official references

Implementation follows Google's current
[Google Gen AI Python SDK documentation](https://github.com/googleapis/python-genai#json-response-schema)
(client setup, JSON Schema/Pydantic structured output, and API errors), retrieved
during implementation. The Google-hosted documentation site was blocked by the
development environment's network proxy; the official SDK documentation was
accessible through GitHub.

- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key)
