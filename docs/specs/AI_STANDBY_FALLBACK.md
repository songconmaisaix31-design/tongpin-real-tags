# AI Standby Fallback Specification

Status: **Implemented and locally verified; live activation blocked by upstream permission**

## Product outcome

When no eligible real person satisfies the existing hard filters, a signed-in
user may enter a clearly labeled AI standby conversation instead of reaching a
dead end. A real person always takes precedence. The AI must never appear to be
or claim to be a human match.

This fallback improves first-use continuity without weakening the product's
trust promise or inserting a synthetic user into the real-user pool.

## Acceptance criteria

1. If `ranked_matches()` returns at least one eligible person, the existing
   human matching flow is unchanged and no AI conversation is created.
2. If no eligible person exists and the AI provider configuration is complete,
   starting a match creates or reuses one AI standby conversation for that
   user and redirects to it.
3. Matching itself performs no model request. A model request occurs only after
   the user knowingly sends a message inside the labeled AI conversation.
4. Every AI surface says `AI standby` / `not a real person` in Chinese UI copy.
   AI conversations expose no match score, profile reveal, contact exchange,
   block-person action, or human-only unlock flow.
5. The model receives only a fixed system instruction and at most the latest 12
   bounded text turns. Email, user ID, alias, profile fields, tags, match
   weights, and raw datasource records are never sent.
6. User messages are stored before the single bounded provider call. On provider
   failure the user message remains, no fabricated reply is stored, and the UI
   reports a safe error without upstream bodies or credentials.
7. Provider responses are treated as untrusted input, require the documented
   JSON shape, are capped at 64 KiB in transit and 500 characters in storage,
   and remain escaped by the existing Jinja template.
8. Each AI conversation has a configurable reply cap. No automatic network
   retries are performed.
9. If configuration is absent or invalid, the current empty-candidate behavior
   remains and existing AI conversations become read-only.
10. A provider credential is accepted only from an encrypted runtime variable,
    or from Vercel's deployment-scoped OIDC token when the endpoint is the exact
    Vercel AI Gateway URL. No secret value enters Git, documentation, logs,
    evidence, the database, browser storage, or project memory.

## Runtime contract

The first adapter is intentionally provider-neutral and uses the common
OpenAI-compatible Chat Completions wire shape. Activation requires the provider
to document this compatibility.

Required runtime configuration:

| Variable | Contract |
| --- | --- |
| `AI_FALLBACK_ENABLED` | Must equal `1` to enable the fallback. |
| `AI_FALLBACK_BASE_URL` | Verified HTTPS provider base URL, without query, fragment, or embedded credentials. |
| `AI_FALLBACK_MODEL` | Exact provider model identifier. |

One authentication source is required:

| Variable | Contract |
| --- | --- |
| `AI_FALLBACK_API_KEY` | Optional secret bearer credential for a verified OpenAI-compatible provider; never persisted or logged. |
| `x-vercel-oidc-token` request header | Automatically supplied to each Vercel Function request and accepted only when the normalized completion URL exactly equals `https://ai-gateway.vercel.sh/v1/chat/completions`. |
| `VERCEL_OIDC_TOKEN` | Build/local fallback only; Vercel does not expose this environment variable to deployed Function runtime code. |

Server-owned defaults:

| Setting | Value |
| --- | --- |
| Endpoint | `{AI_FALLBACK_BASE_URL}/chat/completions` |
| Method | `POST` |
| Timeout | 8 seconds |
| Redirects | Rejected |
| Retries | None |
| Maximum response body | 64 KiB |
| Maximum persisted reply | 500 characters |
| Context window sent | Latest 12 text turns |
| Reply cap | 30 per AI conversation |

Request body:

```json
{
  "model": "<configured model>",
  "messages": [
    {"role": "system", "content": "<server-owned safety prompt>"},
    {"role": "user", "content": "<bounded user message>"}
  ],
  "temperature": 0.8,
  "max_tokens": 180,
  "stream": false
}
```

Accepted response boundary:

```json
{
  "choices": [
    {"message": {"content": "<non-empty string>"}}
  ]
}
```

The production adapter uses Vercel AI Gateway's documented OpenAI-compatible
endpoint and request-scoped deployment OIDC authentication. The selected model is
`alibaba/qwen3.5-flash`. The credential previously posted in chat remains
excluded from runtime configuration and must be treated as exposed.

## Data model

- Add `conversations.counterpart_type`, constrained to `human` or `ai`, with
  `human` as the migration default.
- An AI conversation remains a direct conversation for inbox compatibility but
  has exactly one real `conversation_members` row and no synthetic `users` row.
- AI replies use `messages.sender_id = NULL`, `message_type = text`, and bounded
  metadata `{kind: ai_reply}`.
- The deterministic per-user AI conversation ID makes fallback creation
  idempotent.

## Safety and privacy boundaries

- The server prompt requires Chinese, concise, non-deceptive replies and
  prohibits claims of a real identity, real-world biography, contact exchange,
  or offline meeting.
- The page discloses that typed conversation content is sent to the configured
  model provider.
- The model has no tools, database access, profile context, or secret context.
- Human reports remain available for AI conversations. The human-specific block
  action is not shown and forged block requests are rejected.
- Provider errors log only a bounded internal taxonomy code; upstream response
  bodies, request text, and credentials are neither logged, stored, nor returned
  to users.

## Risks and controls

| Risk | Control |
| --- | --- |
| AI masquerades as a person | Persistent `AI standby / not a real person` labeling and system instruction. |
| Private profile leakage | Text-only bounded context; no profile or datasource fields. |
| Secret leakage | Encrypted provider key or deployment-scoped OIDC only; never logged or stored. |
| Cost or abuse | One call per accepted message, 30-reply cap, 500-character input, no retries. |
| Provider outage | Preserve the user's message, store no fake reply, show safe failure copy. |
| Prompt injection or unsafe output | No tools/secrets, fixed system prompt, bounded escaped output, existing report flow. |
| SSRF or credential forwarding | HTTPS-only validation; reject userinfo, query, fragment, and redirects; permit OIDC only for the exact Gateway endpoint. |

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ai_fallback -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/match_flow.test.mjs tests/registration_draft.test.mjs
.\harness.cmd
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe tools\verify_live_ai_deployment.py https://<isolated-qa-domain> --public
git diff --check
```

Visual verification must cover the empty human pool, persistent AI disclosure,
message composer, provider-failure copy, desktop layout, and 390x844 mobile
layout. Live activation additionally requires a read-only configuration check,
a single controlled model turn with generated test text, and evidence that no
secret or profile field appears in the database or response.

## Local verification result

- Python: 110 tests passed.
- JavaScript: 11 tests passed.
- Harness: 6/6 gates passed with the project virtual environment on `PATH`.
- Python compilation, probe-script compilation, and `git diff --check` passed.

## Live activation result (2026-08-23)

- The sanitized probe reached an isolated Vercel deployment, registered a
  generated QA identity, entered the disclosed AI standby flow, and preserved
  the user's controlled message without exposing its content in evidence.
- Request-scoped Vercel OIDC reached the documented AI Gateway endpoint, but
  the Gateway returned HTTP 403. The bounded application diagnostic was
  `permission_denied`; no upstream response body or credential was logged.
- Read-only checks confirmed that `alibaba/qwen3.5-flash` remained listed with
  an available provider endpoint and that the team had no AI Gateway routing
  rules. Those checks do not prove inference permission or a successful reply.
- Production activation is `HOLD`. This AI runtime candidate was not promoted;
  the concurrent avatar deployment `dpl_GuM7Q9sUNgvewZbr3EzfZqusuqc2` remained
  current at `app.davidwang.space`. Completion requires the account owner to
  resolve the AI Gateway permission boundary and rerun one controlled model turn.
