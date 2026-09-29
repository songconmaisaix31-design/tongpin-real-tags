(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }
  root.MatchFlow = api;
  api.bindMatchSearchPage();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const STEP_TIMELINE = Object.freeze([
    Object.freeze({ key: "filter", delay: 260 }),
    Object.freeze({ key: "similarity", delay: 1000 }),
    Object.freeze({ key: "ranking", delay: 1740 })
  ]);
  const COMPLETE_DELAY = 2500;

  const submitMatchCompletion = (form) => {
    if (!form) {
      return false;
    }
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return true;
    }
    if (typeof form.submit === "function") {
      form.submit();
      return true;
    }
    return false;
  };

  const createMatchTimeline = ({
    reducedMotion = false,
    schedule = (callback, delay) => setTimeout(callback, delay),
    cancelScheduled = (task) => clearTimeout(task),
    onStep = () => {},
    onComplete = () => {}
  } = {}) => {
    let generation = 0;
    let completed = false;
    let tasks = [];

    const clearTasks = () => {
      tasks.forEach((task) => cancelScheduled(task));
      tasks = [];
    };

    const start = () => {
      clearTasks();
      generation += 1;
      completed = false;
      const run = generation;

      const step = (key) => {
        if (run !== generation || completed) {
          return;
        }
        onStep(key);
      };

      const complete = () => {
        if (run !== generation || completed) {
          return;
        }
        completed = true;
        onComplete();
      };

      if (reducedMotion) {
        STEP_TIMELINE.forEach((item) => step(item.key));
        complete();
        return run;
      }

      STEP_TIMELINE.forEach((item) => {
        tasks.push(schedule(() => step(item.key), item.delay));
      });
      tasks.push(schedule(complete, COMPLETE_DELAY));
      return run;
    };

    const cancel = () => {
      generation += 1;
      completed = false;
      clearTasks();
    };

    return {
      start,
      cancel,
      restart: start,
      state: () => ({ generation, completed, pendingTaskCount: tasks.length })
    };
  };

  const bindMatchSearchPage = () => {
    const stage = document.querySelector("[data-match-search]");
    if (!stage) {
      return null;
    }

    const completeForm = stage.querySelector("[data-match-complete]");
    const cancelForm = stage.querySelector("[data-match-cancel]");
    const progress = stage.querySelector("[data-match-progress]");
    const progressFill = progress?.querySelector("span");
    const progressLabel = stage.querySelector("[data-match-progress-label]");
    const live = stage.querySelector("[data-match-live]");
    const steps = Array.from(stage.querySelectorAll("[data-match-step]"));
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const stepOrder = STEP_TIMELINE.map((item) => item.key);
    const progressByStep = { filter: 24, similarity: 57, ranking: 84 };
    const messageByStep = {
      filter: "候选池筛选完成，正在计算真实标签相似度。",
      similarity: "标签相似度计算完成，正在生成匿名排序。",
      ranking: "匿名排序已经完成，正在确认本次结果。"
    };
    let submitTimer = null;

    const setProgress = (value) => {
      const safeValue = Math.max(0, Math.min(100, value));
      progress?.setAttribute("aria-valuenow", String(safeValue));
      if (progressFill) {
        progressFill.style.width = `${safeValue}%`;
      }
      if (progressLabel) {
        progressLabel.textContent = `${safeValue}%`;
      }
    };

    const updateStep = (key) => {
      const activeIndex = stepOrder.indexOf(key);
      steps.forEach((element) => {
        const index = stepOrder.indexOf(element.dataset.matchStep);
        const status = element.querySelector(".match-step-status");
        element.classList.toggle("is-active", index === activeIndex);
        element.classList.toggle("is-complete", index < activeIndex);
        if (status) {
          status.textContent = index < activeIndex ? "完成" : index === activeIndex ? "进行中" : "等待";
        }
      });
      setProgress(progressByStep[key] || 0);
      if (live) {
        live.textContent = messageByStep[key] || "正在继续匹配。";
      }
    };

    const finishView = () => {
      steps.forEach((element) => {
        element.classList.remove("is-active");
        element.classList.add("is-complete");
        const status = element.querySelector(".match-step-status");
        if (status) {
          status.textContent = "完成";
        }
      });
      setProgress(100);
      stage.classList.add("is-complete");
      stage.setAttribute("aria-busy", "false");
      if (live) {
        live.textContent = "已找到一位同频的人，正在打开匿名结果。";
      }
      submitTimer = window.setTimeout(
        () => submitMatchCompletion(completeForm),
        reducedMotion ? 120 : 360
      );
    };

    const timeline = createMatchTimeline({
      reducedMotion,
      onStep: updateStep,
      onComplete: finishView
    });

    const stop = () => {
      timeline.cancel();
      if (submitTimer !== null) {
        window.clearTimeout(submitTimer);
        submitTimer = null;
      }
    };

    completeForm?.addEventListener("submit", stop);
    cancelForm?.addEventListener("submit", stop);
    window.addEventListener("pagehide", stop, { once: true });

    timeline.start();
    return timeline;
  };

  return {
    STEP_TIMELINE,
    COMPLETE_DELAY,
    createMatchTimeline,
    submitMatchCompletion,
    bindMatchSearchPage
  };
});
