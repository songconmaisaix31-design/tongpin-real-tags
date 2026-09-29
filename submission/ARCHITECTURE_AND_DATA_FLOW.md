# Architecture and Data Flow

## System boundary

```text
Browser (ordinary HTML forms)
  -> Flask route and session authorization
  -> server-owned source registry / domain service
  -> validated operation
       -> bounded credential-free Public Live transport
       -> deterministic Fixture generator
       -> explicit Unavailable result
  -> source-specific shape validation and normalized tag mapping
  -> atomic SQLite transaction
  -> Post/Redirect/Get
  -> self-only profile or anonymous projection
```

Flask, Jinja2, and SQLite remain the product runtime. The browser does not
choose a data mode, submit a remote URL, set verification state, or provide a
mapping version. Routes do not receive raw upstream objects, and matching does
not know third-party response fields.

## Public Live success path

```text
validated public handle
  -> fixed HTTPS endpoint, timeout, response cap, no retry
  -> required response-shape validation
  -> allowlisted direct and deterministic-derived tags
  -> one transaction replaces only that user's tags for that source
  -> last-success and attempt metadata update together
```

Public Live means response provenance passed the frozen mapping. Identity
assurance remains `unverified_public_handle`; it is not authentication or
ownership verification.

## Public Live failure path

```text
invalid handle --------------------------> invalid_input; zero transport calls
timeout / network / HTTP / schema failure -> bounded non-ready state
                                            preserve last-success tags
                                            preserve last-success time
                                            never load Fixture automatically
```

Raw bodies, response headers, stack traces, cookies, tokens, and handles are
not valid error content. Expected upstream failures must not become Flask 500
responses.

## Fixture and Unavailable paths

- Fixture values are deterministic synthetic records, `verified=false`,
  `self_only`, and `synthetic_fixture`. Fixture loading is rejected when demo
  mode is disabled.
- Unavailable registry entries have no active form. A forged direct POST must
  return 404 and create no tags or connection state.
- Public Live failure and Fixture loading are different operations. There is no
  automatic fallback between them.

## Privacy projections

| Consumer | Allowed data | Excluded data |
|---|---|---|
| Self profile | Normalized values plus bounded provenance | Raw response, credentials, unnecessary identity fields |
| Matching service | `tag_id` and normalized value after mode eligibility | Handle, source error, response metadata, raw profile |
| Searching and L0 result | Smoothed percentage and hidden-point count | Candidate identity, tags, source provenance, raw score, weights |
| L0 conversation | Anonymous conversation state | Unrevealed profile fields |
| Event host review | Match percentage and common-tag count | Applicant identity |

## Side-effect controls

- Login is required before product mutations.
- Conversation membership is checked before message, tool, report, or block
  operations.
- Invalid forms and stale match attempts write no domain rows.
- Restaurant events accept only server-defined POIs and bounded participant
  counts.
- Public Live success replacement is atomic; non-ready attempts update only
  bounded attempt metadata.

The acceptance runner observes these boundaries through Flask's test client and
a disposable SQLite database. It blocks external socket creation, so its result
is local deterministic evidence only.
