import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const {
  DRAFT_KEY,
  bindRegistrationDraft,
  collectDraft,
  readDraft,
  restoreDraft,
  writeDraft
} = require("../app/static/js/registration-draft.js");

class FakeEvent {
  constructor(type) {
    this.type = type;
  }
}

const fakeField = ({ name, value = "", type = "text", checked = false }) => ({
  name,
  value,
  type,
  checked,
  defaultValue: value,
  defaultChecked: checked,
  events: [],
  ownerDocument: { defaultView: { Event: FakeEvent } },
  dispatchEvent(event) {
    this.events.push(event.type);
  }
});

const fakeForm = (fields) => {
  const listeners = new Map();
  return {
    fields,
    resetCount: 0,
    querySelectorAll(selector) {
      assert.equal(selector, "[name]");
      return fields;
    },
    addEventListener(type, callback) {
      listeners.set(type, callback);
    },
    emit(type) {
      listeners.get(type)?.({ type });
    },
    reset() {
      this.resetCount += 1;
      fields.forEach((field) => {
        field.value = field.defaultValue;
        field.checked = field.defaultChecked;
      });
    }
  };
};

const fakeStorage = (initial = {}) => {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    }
  };
};

const fakePage = ({ auth = "guest", form = null, storage = fakeStorage() } = {}) => {
  const windowListeners = new Map();
  const timers = [];
  const status = { textContent: "刷新或回退会恢复本标签页暂存的资料；密码不会保存。" };
  return {
    storage,
    status,
    documentRef: {
      body: { dataset: { auth } },
      querySelector(selector) {
        if (selector === "[data-registration-draft]") return form;
        if (selector === "[data-registration-draft-status]") return status;
        return null;
      }
    },
    windowRef: {
      sessionStorage: storage,
      addEventListener(type, callback) {
        windowListeners.set(type, callback);
      },
      setTimeout(callback) {
        timers.push(callback);
      }
    },
    emitWindow(type, event = {}) {
      windowListeners.get(type)?.(event);
    },
    runTimers() {
      timers.splice(0).forEach((callback) => callback());
    }
  };
};

test("draft collection persists only allowlisted non-secret fields", () => {
  const form = fakeForm([
    fakeField({ name: "email", value: "person@example.test" }),
    fakeField({ name: "password", value: "must-never-persist", type: "password" }),
    fakeField({ name: "anonymous_alias", value: "回退旅人" }),
    fakeField({ name: "purposes", value: "学习搭子", type: "checkbox", checked: true }),
    fakeField({ name: "purposes", value: "饭搭子", type: "checkbox", checked: false }),
    fakeField({ name: "unexpected_future_field", value: "not-allowed" })
  ]);

  const draft = collectDraft(form);

  assert.equal(draft.values.email, "person@example.test");
  assert.equal(draft.values.anonymous_alias, "回退旅人");
  assert.deepEqual(draft.values.purposes, ["学习搭子"]);
  assert.equal(Object.hasOwn(draft.values, "password"), false);
  assert.equal(Object.hasOwn(draft.values, "unexpected_future_field"), false);
  assert.equal(JSON.stringify(draft).includes("must-never-persist"), false);
});

test("draft restoration restores scalar and checkbox values exactly", () => {
  const email = fakeField({ name: "email" });
  const selected = fakeField({ name: "interests", value: "阅读", type: "checkbox" });
  const unselected = fakeField({ name: "interests", value: "游戏", type: "checkbox", checked: true });
  const password = fakeField({ name: "password", value: "browser-owned", type: "password" });
  const form = fakeForm([email, selected, unselected, password]);

  const restored = restoreDraft(form, {
    version: 1,
    values: { email: "restored@example.test", interests: ["阅读"], password: "ignored" }
  });

  assert.equal(restored, true);
  assert.equal(email.value, "restored@example.test");
  assert.equal(selected.checked, true);
  assert.equal(unselected.checked, false);
  assert.equal(password.value, "browser-owned");
  assert.deepEqual(email.events, ["input"]);
  assert.deepEqual(selected.events, ["change"]);
});

test("storage round trip rejects malformed drafts without blocking the form", () => {
  const storage = fakeStorage({ [DRAFT_KEY]: "{not-json" });
  assert.equal(readDraft(storage), null);
  assert.equal(storage.getItem(DRAFT_KEY), null);

  const form = fakeForm([fakeField({ name: "city", value: "上海" })]);
  assert.equal(writeDraft(storage, collectDraft(form)), true);
  assert.equal(readDraft(storage).values.city, "上海");
});

test("page lifecycle restores history state and authenticated pages clear it", () => {
  const email = fakeField({ name: "email", value: "first@example.test" });
  const form = fakeForm([email]);
  const page = fakePage({ form });
  const binding = bindRegistrationDraft(page);

  assert.equal(binding.state, "bound");
  form.emit("input");
  email.value = "";
  page.emitWindow("pageshow", { persisted: true });
  assert.equal(email.value, "");
  page.runTimers();
  assert.equal(email.value, "first@example.test");
  assert.match(page.status.textContent, /已恢复/);

  const signedInPage = fakePage({ auth: "signed-in", storage: page.storage });
  assert.equal(bindRegistrationDraft(signedInPage).state, "cleared");
  assert.equal(page.storage.getItem(DRAFT_KEY), null);

  email.value = "stale@example.test";
  page.emitWindow("pageshow", { persisted: true });
  page.runTimers();
  assert.equal(form.resetCount, 1);
  assert.equal(email.value, "first@example.test");
});
