const form = document.getElementById("record-form");
const referenceInput = document.getElementById("record-reference");
const repositorySelect = document.getElementById("repository-select");
const repositoryLink = document.getElementById("repository-link");
const submitButton = document.getElementById("submit-button");
const statusOutput = document.getElementById("status");
const repositoryOutput = document.getElementById("repository-output");
const recordOutput = document.getElementById("record-checks-output");
const aggregatorOutput = document.getElementById("aggregator-checks-output");
const scoresOutput = document.getElementById("scores-output");
let definitions;
let currentChecks = [];
let currentGroups = [];
let currentAggregators = [];
let rawFields = [];
let highlightedFields = [];

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusBadge(status) {
  if (!status) return document.createTextNode("");
  if (status === "RUNNING") {
    const spinner = element("span", "check-spinner");
    spinner.setAttribute("role", "status");
    spinner.setAttribute("aria-label", "Check in progress");
    spinner.title = "Check in progress";
    return spinner;
  }
  return element("span", `check-${status.toLowerCase()}`, `[${status}]`);
}

function hasFujiOverlap(check) {
  return Boolean(check.fujiOverlap || check.duplicateOf?.length);
}

function renderScores(checks, evaluated = false) {
  scoresOutput.replaceChildren();
  const buckets = [
    ["Own checks", checks.filter((check) => !hasFujiOverlap(check))],
    ["F-UJI overlap", checks.filter(hasFujiOverlap)],
    ["All checks", checks],
  ];
  buckets.forEach(([label, items]) => {
    const applicable = items.filter((check) => check.status !== "NOT_APPLICABLE");
    const passed = applicable.filter((check) => check.status === "PASS").length;
    const score = evaluated ? `${passed} / ${applicable.length} PASS` : `— / ${items.length} PASS`;
    const card = element("article", "score-card");
    card.append(element("h3", "score-label", label), element("p", "score-value", score));
    scoresOutput.append(card);
  });
}

function fact(list, label, content) {
  list.append(element("dt", null, label), content);
}

function renderMappedFields(fields = []) {
  const description = element("dd");
  if (!fields.length) description.textContent = "No native fields are mapped.";
  fields.forEach(({binding, paths}) => {
    const line = element("span", "mapped-field");
    line.append(`${binding}: `);
    paths.forEach((path, index) => {
      if (index) line.append(", ");
      const button = element("button", "mapped-field-link", path);
      button.type = "button";
      button.disabled = !findRawFields(path).length;
      button.title = button.disabled ? "" : "Highlight in Raw response";
      button.setAttribute("aria-controls", "repository-output");
      button.addEventListener("click", () => highlightMappedField(path));
      line.append(button);
    });
    description.append(line);
  });
  return description;
}

function renderStep(step) {
  const details = element("details", "check-step");
  const summary = element("summary");
  const label = step.operation === "REDUCE" ? "Apply the fixed pass rule" : step.label;
  summary.append(statusBadge(step.status), ` ${step.number}. ${step.operation} — ${label}`,
    element("span", "step-method", step.method));
  details.append(summary);
  details.addEventListener("toggle", () => {
    if (!details.open || details.childElementCount > 1) return;
    const body = element("div", "step-body");
    body.append(element("p", null, step.message));
    if (step.executed !== false) {
      for (const [title, value] of [["Inputs", step.input], ["Output", step.output]]) {
        body.append(element("h5", null, title), element("pre", null, JSON.stringify(value, null, 2)));
      }
    }
    details.append(body);
  });
  return details;
}

function renderCheck(check) {
  const article = element("article", "individual-check");
  article.dataset.checkId = check.testId;
  article.setAttribute("aria-busy", String(check.status === "RUNNING"));
  const heading = element("h4", "check-title");
  const title = element("span");
  title.append(statusBadge(check.status), ` ${check.testId} ${check.label}`);
  heading.append(title);
  if (hasFujiOverlap(check)) {
    const badge = element("span", "fuji-badge", "F-UJI");
    badge.title = check.fujiOverlap || `Equivalent to ${check.duplicateOf.join(", ")}`;
    heading.append(badge);
  }
  const facts = element("dl", "check-facts");
  fact(facts, "Mapped fields:", renderMappedFields(check.mappedFields));
  fact(facts, "Pass rule:", element("dd", null, check.passRule));
  fact(facts, "Searchability benefit:", element("dd", null, check.searchabilityBenefit));
  article.append(heading);
  if (check.status === "ERROR" && check.message) article.append(element("p", "error", check.message));
  article.append(facts, element("hr", "check-divider"));
  if (check.steps) {
    check.steps.forEach((step) => article.append(renderStep(step)));
  } else {
    (check.plannedSteps || []).forEach((step, index) => {
      const planned = element("details", "check-step");
      const summary = element("summary", null, `${index + 1}. ${step.operations.join(" → ") || step.method}`);
      planned.append(summary, element("p", "step-body", step.description));
      article.append(planned);
    });
  }
  return article;
}

function groupStatus(checks) {
  if (checks.some((check) => check.status === "RUNNING")) return "RUNNING";
  if (!checks.length || checks.some((check) => !check.status)) return undefined;
  const active = checks.filter((check) => check.status !== "NOT_APPLICABLE");
  if (!active.length) return "NOT_APPLICABLE";
  if (active.some((check) => check.status === "FAIL")) return "FAIL";
  return active.every((check) => check.status === "PASS") ? "PASS" : "UNSURE";
}

function renderGroupSummary(group, checks) {
  const summary = element("summary");
  summary.append(statusBadge(group.status ?? groupStatus(checks)),
    element("span", null, `${group.group || group.id} ${group.label || group.title}`),
    element("span", "group-count", `${checks.length} checks · ${checks.filter((check) => check.status === "PASS").length} PASS`));
  return summary;
}

function renderGroups(output, checks, groups) {
  const openGroups = new Map([...output.querySelectorAll(".check-group")].map((group) => [group.dataset.group, group.open]));
  output.replaceChildren();
  const controls = element("div", "check-controls");
  [["Expand groups", true], ["Collapse groups", false]].forEach(([label, open]) => {
    const button = element("button", null, label);
    button.type = "button";
    button.addEventListener("click", () => output.querySelectorAll(".check-group").forEach((group) => { group.open = open; }));
    controls.append(button);
  });
  output.append(controls);
  groups.forEach((group) => {
    const id = group.group || group.id;
    const items = checks.filter((check) => check.group === id);
    const section = element("details", "check-group");
    section.dataset.group = id;
    section.open = openGroups.get(id) ?? false;
    const summary = renderGroupSummary(group, items);
    const body = element("div", "group-checks");
    items.forEach((check) => body.append(renderCheck(check)));
    section.append(summary, body);
    output.append(section);
  });
}

function renderAggregators(checks) {
  aggregatorOutput.replaceChildren();
  checks.forEach((check) => {
    const article = element("article", "individual-check");
    article.setAttribute("aria-busy", String(check.status === "RUNNING"));
    const title = element("h4", "check-title");
    title.append(statusBadge(check.status), ` ${check.label}`);
    article.append(title);
    if (check.message) article.append(element("p", null, check.message));
    article.append(element("p", null, `DOI: ${check.doi || "Unavailable"}`));
    if (check.sourceUrl) {
      try {
        const url = new URL(check.sourceUrl);
        if (["http:", "https:"].includes(url.protocol)) {
          const link = element("a", null, "Lookup source");
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          article.append(link);
        }
      } catch { /* A malformed source is displayed through the result, never executed. */ }
    }
    aggregatorOutput.append(article);
  });
}

function pendingChecks() {
  currentChecks = definitions ? definitions.checks.map((check) => ({...check})) : [];
  currentGroups = definitions?.groups || [];
  renderScores(currentChecks);
  renderGroups(recordOutput, currentChecks, currentGroups);
}

function updateGroupSummaries() {
  recordOutput.querySelectorAll(".check-group").forEach((section) => {
    const group = currentGroups.find((item) => (item.group || item.id) === section.dataset.group);
    const checks = currentChecks.filter((check) => check.group === section.dataset.group);
    const summary = section.querySelector("summary");
    summary.replaceChildren(...renderGroupSummary(group, checks).childNodes);
  });
}

function updateCheck(check) {
  const index = currentChecks.findIndex((item) => item.testId === check.testId);
  if (index < 0) throw new Error("The stream returned a check outside the loaded catalogue.");
  currentChecks[index] = {...currentChecks[index], ...check};
  const article = [...recordOutput.querySelectorAll(".individual-check")].find((node) => node.dataset.checkId === check.testId);
  article.replaceWith(renderCheck(currentChecks[index]));
  updateGroupSummaries();
  renderScores(currentChecks, currentChecks.some((item) => item.status && item.status !== "RUNNING"));
}

function updateAggregator(check) {
  const index = currentAggregators.findIndex((item) => item.label === check.label);
  if (index < 0) currentAggregators.push(check);
  else currentAggregators[index] = check;
  renderAggregators(currentAggregators);
}

function clearRepositoryResponse(message = "") {
  rawFields = [];
  highlightedFields = [];
  repositoryOutput.textContent = message;
  updateMappedFieldLinks();
}

function renderResponseValue(value, path = [], depth = 0) {
  const node = element("span");
  rawFields.push({path, node});
  if (value !== null && typeof value === "object") {
    const array = Array.isArray(value);
    const entries = Object.entries(value);
    node.append(array ? "[" : "{");
    entries.forEach(([key, item], index) => {
      node.append("\n" + "  ".repeat(depth + 1));
      const child = renderResponseValue(item, [...path, array ? Number(key) : key], depth + 1);
      if (!array) child.prepend(`${JSON.stringify(key)}: `);
      if (index < entries.length - 1) child.append(",");
      node.append(child);
    });
    if (entries.length) node.append("\n" + "  ".repeat(depth));
    node.append(array ? "]" : "}");
  } else {
    node.textContent = JSON.stringify(value);
  }
  return node;
}

function showRepositoryResponse(response) {
  clearRepositoryResponse();
  repositoryOutput.replaceChildren(renderResponseValue(response));
  repositoryOutput.scrollTop = 0;
  repositoryOutput.scrollLeft = 0;
  updateMappedFieldLinks();
}

function findRawFields(path) {
  const parts = [...path.matchAll(/([^.[\]]+)|\[(\d*)\]/g)]
    .map(([, key, index]) => key ?? (index === "" ? null : Number(index)));
  return rawFields.filter((field) => field.path.length === parts.length && parts.every((part, index) =>
    part === null ? typeof field.path[index] === "number" : part === field.path[index])).map((field) => field.node);
}

function updateMappedFieldLinks() {
  recordOutput.querySelectorAll(".mapped-field-link").forEach((button) => {
    button.disabled = !findRawFields(button.textContent).length;
    button.title = button.disabled ? "" : "Highlight in Raw response";
  });
}

function highlightMappedField(path) {
  highlightedFields.forEach((node) => node.classList.remove("raw-field-highlight"));
  highlightedFields = findRawFields(path);
  highlightedFields.forEach((node) => node.classList.add("raw-field-highlight"));
  if (!highlightedFields.length) return;
  repositoryOutput.scrollTop += highlightedFields[0].getBoundingClientRect().top
    - repositoryOutput.getBoundingClientRect().top - repositoryOutput.clientHeight / 3;
  repositoryOutput.scrollLeft = 0;
  repositoryOutput.scrollIntoView({block: "nearest", inline: "nearest"});
}

function finishEvaluation(result) {
  if (!currentChecks.length) throw new Error("The check catalogue could not be loaded.");
  result.checks.recordLevel.forEach((check) => {
    const existing = currentChecks.find((item) => item.testId === check.testId);
    if (!existing?.status || existing.status === "RUNNING" || existing.status !== check.status) updateCheck(check);
  });
  currentGroups = result.summary.groups;
  updateGroupSummaries();
  renderScores(result.checks.recordLevel, true);
  currentAggregators = result.checks.aggregators;
  renderAggregators(currentAggregators);
  statusOutput.textContent = result.metadataProvider ? `${result.metadataProvider} · ${result.resolvedDoi}` : "Evaluation complete.";
}

function applyEvaluationEvent(update) {
  switch (update.event) {
    case "record_loaded":
      definitions = update.catalogue;
      pendingChecks();
      showRepositoryResponse(update.repositoryResponse);
      break;
    case "check_started": {
      updateCheck({testId: update.testId, status: "RUNNING"});
      const check = currentChecks.find((item) => item.testId === update.testId);
      statusOutput.textContent = `Checking ${check.testId} — ${check.label}`;
      break;
    }
    case "check_finished":
      updateCheck(update.check);
      statusOutput.textContent = `${currentChecks.filter((check) => check.status && check.status !== "RUNNING").length} / ${currentChecks.length} checks complete`;
      break;
    case "aggregator_started":
      updateAggregator({label: update.label, doi: update.doi, status: "RUNNING"});
      statusOutput.textContent = "Checking aggregators…";
      break;
    case "aggregator_finished":
      updateAggregator(update.check);
      break;
    case "evaluation_finished":
      finishEvaluation(update.result);
      break;
    case "evaluation_error":
      throw new Error(update.error || "Evaluation failed.");
  }
}

async function readEvaluationStream(response, onEvent) {
  if (!response.body) throw new Error("Streaming responses are unavailable in this browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  const consume = (line) => {
    if (!line.trim()) return;
    const update = JSON.parse(line);
    onEvent(update);
    if (update.event === "evaluation_finished") finished = true;
  };
  try {
    while (!finished) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      let newline;
      while (!finished && (newline = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        consume(line);
      }
      if (done) {
        if (!finished && buffer.trim()) consume(buffer);
        break;
      }
    }
    if (!finished) throw new Error("The evaluation connection ended before all results arrived. Please retry.");
  } finally {
    try { await reader.cancel(); } finally { reader.releaseLock(); }
  }
}

function interruptEvaluation(message) {
  currentChecks.filter((check) => check.status === "RUNNING").forEach((check) => updateCheck({...check, status: "ERROR", message}));
  currentAggregators.filter((check) => check.status === "RUNNING").forEach((check) => updateAggregator({...check, status: "ERROR", message}));
}

async function loadDefinitions() {
  try {
    const response = await fetch(`/catalogue?repository=${encodeURIComponent(repositorySelect.value)}`);
    if (!response.ok) throw new Error("The fixed check catalogue could not be loaded.");
    definitions = await response.json();
    if (!submitButton.disabled) pendingChecks();
  } catch (error) {
    if (!submitButton.disabled) statusOutput.textContent = error.message;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  repositorySelect.disabled = true;
  statusOutput.classList.remove("error");
  statusOutput.textContent = "Loading and checking…";
  clearRepositoryResponse("Loading and checking…");
  currentAggregators = [];
  aggregatorOutput.replaceChildren();
  pendingChecks();
  let recordLoaded = false;
  try {
    const response = await fetch("/evaluate", {method: "POST", headers: {"Content-Type": "application/json", "Accept": "application/x-ndjson"},
      body: JSON.stringify({reference: referenceInput.value.trim(), repository: repositorySelect.value})});
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error || "Evaluation failed.");
    }
    await readEvaluationStream(response, (update) => {
      if (update.event === "record_loaded") recordLoaded = true;
      applyEvaluationEvent(update);
    });
  } catch (error) {
    statusOutput.classList.add("error");
    statusOutput.textContent = error.message || "Evaluation failed.";
    interruptEvaluation(statusOutput.textContent);
    if (!recordLoaded) clearRepositoryResponse();
  } finally {
    submitButton.disabled = false;
    repositorySelect.disabled = false;
  }
});

function updateRepositoryLink() {
  const repositories = {
    zenodo: ["Zenodo", "https://zenodo.org/", "10.5281/zenodo.3357455"],
    icpsr: ["ICPSR", "https://www.icpsr.umich.edu/sites/icpsr/home", "10.3886/ICPSR35300.v3"],
    opencontext: ["Open Context", "https://opencontext.org/", "10.6078/M7N014GK"],
    metabolights: ["MetaboLights", "https://www.ebi.ac.uk/metabolights/", "MTBLS1"],
    mast: ["MAST", "https://archive.stsci.edu/", "JWST/jw01541005001_0210h_00001_nis"],
  };
  const [name, url, example] = repositories[repositorySelect.value];
  repositoryLink.textContent = name;
  repositoryLink.href = url;
  referenceInput.placeholder = repositorySelect.value === "mast"
    ? `MAST obsid or collection/obs_id, e.g. ${example}`
    : repositorySelect.value === "metabolights"
      ? `MetaboLights accession or study URL, e.g. ${example}`
      : `${name} DOI, record URL or ID, e.g. ${example}`;
  referenceInput.ariaLabel = referenceInput.placeholder;
  if (Object.values(repositories).some(([, , value]) => referenceInput.value.trim() === value)) {
    referenceInput.value = example;
  }
}

repositorySelect.addEventListener("change", () => {
  clearRepositoryResponse();
  updateRepositoryLink();
  loadDefinitions();
});

updateRepositoryLink();
loadDefinitions();
