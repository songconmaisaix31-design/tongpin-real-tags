(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }
  root.RegistrationDraft = api;
  api.bindRegistrationDraft();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DRAFT_KEY = "realtags.registration-draft.v1";
  const DRAFT_VERSION = 1;
  const MAX_SERIALIZED_BYTES = 8192;
  const FIELD_RULES = Object.freeze({
    email: Object.freeze({ kind: "single", maxLength: 254 }),
    anonymous_alias: Object.freeze({ kind: "single", maxLength: 20 }),
    city: Object.freeze({ kind: "single", maxLength: 32 }),
    birth_year: Object.freeze({ kind: "single", maxLength: 4 }),
    gender: Object.freeze({ kind: "single", maxLength: 16 }),
    match_gender: Object.freeze({ kind: "single", maxLength: 16 }),
    schedule: Object.freeze({ kind: "single", maxLength: 32 }),
    mbti: Object.freeze({ kind: "single", maxLength: 8 }),
    zodiac: Object.freeze({ kind: "single", maxLength: 16 }),
    purposes: Object.freeze({ kind: "multiple", maxItems: 6, maxLength: 32 }),
    interests: Object.freeze({ kind: "multiple", maxItems: 12, maxLength: 32 })
  });

  const boundedString = (value, maxLength) => {
    if (typeof value !== "string") {
      return null;
    }
    return value.slice(0, maxLength);
  };

  const formControls = (form) => Array.from(form.querySelectorAll("[name]"));

  const collectDraft = (form) => {
    const controls = formControls(form);
    const values = {};

    Object.entries(FIELD_RULES).forEach(([name, rule]) => {
      const namedControls = controls.filter((control) => control.name === name);

      if (rule.kind === "multiple") {
        values[name] = namedControls
          .filter((control) => control.type === "checkbox" && control.checked)
          .map((control) => boundedString(String(control.value || ""), rule.maxLength))
          .filter(Boolean)
          .slice(0, rule.maxItems);
        return;
      }

      const control = namedControls.find((candidate) => candidate.type !== "password");
      values[name] = boundedString(String(control?.value || ""), rule.maxLength) || "";
    });

    return { version: DRAFT_VERSION, values };
  };

  const sanitizeDraft = (candidate) => {
    if (
      !candidate
      || candidate.version !== DRAFT_VERSION
      || !candidate.values
      || typeof candidate.values !== "object"
      || Array.isArray(candidate.values)
    ) {
      return null;
    }

    const values = {};
    Object.entries(FIELD_RULES).forEach(([name, rule]) => {
      if (!Object.prototype.hasOwnProperty.call(candidate.values, name)) {
        return;
      }

      const storedValue = candidate.values[name];
      if (rule.kind === "multiple") {
        if (!Array.isArray(storedValue)) {
          return;
        }
        values[name] = Array.from(
          new Set(
            storedValue
              .map((value) => boundedString(value, rule.maxLength))
              .filter(Boolean)
          )
        ).slice(0, rule.maxItems);
        return;
      }

      const value = boundedString(storedValue, rule.maxLength);
      if (value !== null) {
        values[name] = value;
      }
    });

    return { version: DRAFT_VERSION, values };
  };

  const hasDraftValues = (draft) => Object.values(draft.values).some((value) => (
    Array.isArray(value) ? value.length > 0 : value.length > 0
  ));

  const notifyControlChanged = (control) => {
    const EventConstructor = control.ownerDocument?.defaultView?.Event;
    if (typeof control.dispatchEvent !== "function" || typeof EventConstructor !== "function") {
      return;
    }
    const eventName = control.type === "checkbox" ? "change" : "input";
    control.dispatchEvent(new EventConstructor(eventName, { bubbles: true }));
  };

  const restoreDraft = (form, candidate) => {
    const draft = sanitizeDraft(candidate);
    if (!draft) {
      return false;
    }

    formControls(form).forEach((control) => {
      const rule = FIELD_RULES[control.name];
      if (!rule || !Object.prototype.hasOwnProperty.call(draft.values, control.name)) {
        return;
      }

      if (rule.kind === "multiple") {
        control.checked = draft.values[control.name].includes(String(control.value));
      } else if (control.type !== "password") {
        control.value = draft.values[control.name];
      }
      notifyControlChanged(control);
    });

    return hasDraftValues(draft);
  };

  const clearDraft = (storage) => {
    try {
      storage?.removeItem(DRAFT_KEY);
      return true;
    } catch (_error) {
      return false;
    }
  };

  const readDraft = (storage) => {
    try {
      const serialized = storage?.getItem(DRAFT_KEY);
      if (!serialized || serialized.length > MAX_SERIALIZED_BYTES) {
        if (serialized) {
          clearDraft(storage);
        }
        return null;
      }
      const draft = sanitizeDraft(JSON.parse(serialized));
      if (!draft) {
        clearDraft(storage);
      }
      return draft;
    } catch (_error) {
      clearDraft(storage);
      return null;
    }
  };

  const writeDraft = (storage, candidate) => {
    const draft = sanitizeDraft(candidate);
    if (!draft || !hasDraftValues(draft)) {
      return clearDraft(storage);
    }

    try {
      const serialized = JSON.stringify(draft);
      if (serialized.length > MAX_SERIALIZED_BYTES) {
        return false;
      }
      storage?.setItem(DRAFT_KEY, serialized);
      return true;
    } catch (_error) {
      return false;
    }
  };

  const availableStorage = (windowRef) => {
    try {
      return windowRef.sessionStorage;
    } catch (_error) {
      return null;
    }
  };

  const bindRegistrationDraft = ({
    documentRef = document,
    windowRef = window,
    storage = availableStorage(windowRef)
  } = {}) => {
    if (!storage) {
      return null;
    }

    if (documentRef.body?.dataset.auth === "signed-in") {
      clearDraft(storage);
      return { state: "cleared" };
    }

    const form = documentRef.querySelector("[data-registration-draft]");
    if (!form) {
      return null;
    }

    const status = documentRef.querySelector("[data-registration-draft-status]");
    const restore = () => {
      const restored = restoreDraft(form, readDraft(storage));
      if (restored && status) {
        status.textContent = "已恢复本标签页暂存的注册资料；密码未保存。";
      }
      return restored;
    };
    const save = () => writeDraft(storage, collectDraft(form));

    restore();
    form.addEventListener("input", save);
    form.addEventListener("change", save);
    windowRef.addEventListener("pagehide", save);
    windowRef.addEventListener("pageshow", (event) => {
      const syncHistoryState = () => {
        if (readDraft(storage)) {
          restore();
          return;
        }
        if (event.persisted) {
          form.reset();
          formControls(form).forEach(notifyControlChanged);
        }
      };

      if (event.persisted && typeof windowRef.setTimeout === "function") {
        windowRef.setTimeout(syncHistoryState, 0);
        return;
      }
      syncHistoryState();
    });

    return { state: "bound", save, restore };
  };

  return {
    DRAFT_KEY,
    DRAFT_VERSION,
    FIELD_RULES,
    collectDraft,
    sanitizeDraft,
    restoreDraft,
    readDraft,
    writeDraft,
    clearDraft,
    bindRegistrationDraft
  };
});
