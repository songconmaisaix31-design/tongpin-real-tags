import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { createMatchTimeline, submitMatchCompletion } = require("../app/static/js/match-flow.js");

const fakeScheduler = () => {
  const tasks = [];
  return {
    tasks,
    schedule(callback, delay) {
      const task = { callback, delay, cancelled: false };
      tasks.push(task);
      return task;
    },
    cancel(task) {
      task.cancelled = true;
    },
    runAll({ includeCancelled = false } = {}) {
      [...tasks]
        .sort((left, right) => left.delay - right.delay)
        .forEach((task) => {
          if (includeCancelled || !task.cancelled) task.callback();
        });
    }
  };
};

test("full motion follows filter, similarity, ranking, complete exactly once", () => {
  const scheduler = fakeScheduler();
  const events = [];
  const timeline = createMatchTimeline({
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    onStep: (key) => events.push(key),
    onComplete: () => events.push("complete")
  });

  timeline.start();
  scheduler.runAll();
  scheduler.runAll();
  assert.deepEqual(events, ["filter", "similarity", "ranking", "complete"]);
});

test("reduced motion completes synchronously without scheduling delays", () => {
  const scheduler = fakeScheduler();
  const events = [];
  createMatchTimeline({
    reducedMotion: true,
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    onStep: (key) => events.push(key),
    onComplete: () => events.push("complete")
  }).start();

  assert.equal(scheduler.tasks.length, 0);
  assert.deepEqual(events, ["filter", "similarity", "ranking", "complete"]);
});

test("cancel invalidates queued callbacks even if they are forced to run", () => {
  const scheduler = fakeScheduler();
  const events = [];
  const timeline = createMatchTimeline({
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    onStep: (key) => events.push(key),
    onComplete: () => events.push("complete")
  });

  timeline.start();
  timeline.cancel();
  scheduler.runAll({ includeCancelled: true });
  assert.deepEqual(events, []);
});

test("restart invalidates the old generation and only the new run completes", () => {
  const scheduler = fakeScheduler();
  const events = [];
  const timeline = createMatchTimeline({
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    onStep: (key) => events.push(key),
    onComplete: () => events.push("complete")
  });

  timeline.start();
  const oldTasks = [...scheduler.tasks];
  timeline.restart();
  oldTasks.forEach((task) => task.callback());
  scheduler.runAll();
  assert.deepEqual(events, ["filter", "similarity", "ranking", "complete"]);
});

test("completion uses requestSubmit when the modern form API is available", () => {
  const calls = [];
  const submitted = submitMatchCompletion({
    requestSubmit: () => calls.push("requestSubmit"),
    submit: () => calls.push("submit")
  });

  assert.equal(submitted, true);
  assert.deepEqual(calls, ["requestSubmit"]);
});

test("completion falls back to native submit in legacy WebViews", () => {
  const calls = [];
  const submitted = submitMatchCompletion({ submit: () => calls.push("submit") });

  assert.equal(submitted, true);
  assert.deepEqual(calls, ["submit"]);
});

test("completion fails closed when no form can be submitted", () => {
  assert.equal(submitMatchCompletion(null), false);
  assert.equal(submitMatchCompletion({}), false);
});
