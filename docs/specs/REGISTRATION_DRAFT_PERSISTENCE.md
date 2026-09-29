# Registration Draft Persistence Specification

## Objective

Preserve a visitor's non-secret registration fields when the same browser tab
is refreshed or navigates away and back. The behavior must reduce accidental
form loss without turning the browser into long-term personal-data storage.

## User-visible contract

- The registration page explains that entered profile data is temporarily
  saved in the current tab.
- A refresh restores supported text, number, select, and multi-select fields.
- Navigating to another page and returning with browser history restores the
  same supported fields.
- The password is never written to Web Storage and must be entered again when
  the browser does not retain it natively.
- A successful registration clears the draft before the user can begin a new
  registration flow.

## Storage contract

- Use `sessionStorage`, not `localStorage`. The draft therefore survives reload
  and same-tab history navigation but expires when the tab session ends.
- Use one versioned key: `realtags.registration-draft.v1`.
- Persist only this allowlist: `email`, `anonymous_alias`, `city`,
  `birth_year`, `gender`, `match_gender`, `schedule`, `mbti`, `zodiac`,
  `purposes`, and `interests`.
- Never persist `password`, cookies, authorization data, hidden fields, or
  arbitrary future form controls.
- Treat stored JSON as untrusted input. Validate its version, field types,
  array sizes, and string lengths before applying it to the DOM.
- If Web Storage is unavailable, full, or malformed, keep the registration
  form usable and discard only the invalid draft.

## Implementation tasks

1. Mark the registration form and its status copy with stable data attributes.
2. Add one dependency-free browser module that serializes the allowlisted
   fields, restores them, and binds `input`, `change`, `pagehide`, and
   `pageshow` lifecycle events.
3. Load the module from the shared shell so any authenticated page can clear a
   completed registration draft after the server redirect.
4. Add Node tests for serialization, restoration, malformed storage, history
   restoration, and authenticated clearing.
5. Add server-rendering tests for the script, form hook, user-facing copy, and
   the explicit password exclusion.

## Acceptance criteria

1. Entered non-secret profile fields survive a real browser refresh.
2. Entered non-secret profile fields survive navigation away and browser Back.
3. Checkbox selections restore exactly; unchecked choices remain unchecked.
4. The password value is absent from serialized draft JSON.
5. Successful authentication removes the registration draft.
6. Invalid or unavailable `sessionStorage` does not prevent registration.
7. Existing server validation, registration, automatic login, and no-Fixture
   production boundaries remain unchanged.
8. Focused browser-script tests, the full Python suite, the HTTP workflow
   harness, syntax compilation, and `git diff --check` pass.

## Risks and controls

- **Personal-data retention:** same-tab storage only, explicit allowlist,
  successful-registration cleanup, and no password storage.
- **Tampered browser data:** bounded validation plus current form options as the
  final accepted value set.
- **Back-forward cache:** save on `pagehide`, restore on `pageshow`, and reset a
  cached registration form after an authenticated page clears the draft.
- **Storage exceptions:** all reads, writes, and removals fail open without
  blocking the form.

## Verification commands

```powershell
node --test tests\registration_draft.test.mjs tests\match_flow.test.mjs
.\.venv\Scripts\python.exe -m unittest tests.test_real_user_environment tests.test_judge_experience -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q app tests tools run_real_user_test.py
.\harness.cmd
git diff --check
```
