export const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export type Task = {
  id: number;
  task_code?: string;
  task_type?: string;
  target_text: string;
  issue_types?: string[];
  focus_words: string[];
  speaking_target: string;
  difficulty: string;
  model_audio_path: string;
  feedback_allowed?: boolean;
  revision_allowed?: boolean;
  active?: boolean;
  created_at: string;
};

export type Attempt = {
  id: number;
  participant_id: string;
  task_id: number;
  group_id: string;
  attempt_number: number;
  audio_path?: string;
  asr_transcript: string;
  duration_seconds: number;
  speech_rate_wpm: number;
  word_match_score: number;
  missing_words: string[];
  substitutions: { expected: string; heard: string }[];
  long_pause_count: number;
  feedback_type: string;
  feedback_use_state?: string;
  feedback_viewed?: boolean;
  re_recorded?: boolean;
  task_type?: string;
  condition?: string;
  feedback: Record<string, string | number>;
  created_at: string;
  target_text: string;
  score: number;
  improvement: number;
};

type Summary = {
  participants: number;
  attempts: number;
  average_attempts_per_task: number;
  average_word_match_score: number;
  average_speech_rate_wpm: number;
  common_missing_words: { word: string; count: number }[];
  common_substitutions: { substitution: string; count: number }[];
  average_improvement_first_to_latest: number;
  feedback_views: number;
  revision_events: number;
};

const TASK_KEY = "speechFeedbackDemoTasks";
const ATTEMPT_KEY = "speechFeedbackDemoAttempts";
const ANNOTATION_KEY = "speechFeedbackDemoAnnotations";

const defaultTasks: Task[] = [
  ["The thin path winds through three quiet fields.", ["thin", "through", "three"], "theta and rhythm", "medium"],
  ["Ray left a red ribbon near the library rail.", ["ray", "red", "ribbon", "library"], "r and l contrast", "medium"],
  ["Please keep the final sound in kept, asked, and missed.", ["kept", "asked", "missed"], "final consonants", "hard"],
  ["A small blue clock stood beside the glass plant.", ["small", "blue", "clock", "glass"], "consonant clusters", "hard"],
  ["She thought the weather would improve by Thursday.", ["thought", "weather", "Thursday"], "th sounds", "hard"],
  ["Mark brought fresh fruit for breakfast before class.", ["brought", "fresh", "fruit", "breakfast"], "clusters and stress", "medium"],
  ["The light rain fell slowly on the river road.", ["light", "rain", "river", "road"], "l and r contrast", "easy"],
  ["We watched the brave child climb the steep steps.", ["watched", "brave", "child", "steep", "steps"], "final sounds and clusters", "hard"],
  ["Laura rarely arrives late for reading lessons.", ["Laura", "rarely", "late", "reading"], "r and l contrast", "medium"],
  ["The student explained the problem in a clear voice.", ["student", "explained", "problem", "clear"], "stress and clarity", "medium"],
  ["I placed the black cup next to the green plate.", ["placed", "black", "cup", "green", "plate"], "clusters", "medium"],
  ["Those three brothers breathe slowly before speaking.", ["those", "three", "brothers", "breathe"], "voiced and voiceless th", "hard"],
  ["The last train stopped at the old stone bridge.", ["last", "stopped", "old", "stone", "bridge"], "final consonants", "medium"],
  ["Fresh spring flowers grow beside the playground.", ["fresh", "spring", "flowers", "grow", "playground"], "clusters and rhythm", "hard"],
  ["Please read each phrase with strong sentence stress.", ["read", "phrase", "strong", "stress"], "stress", "medium"],
  ["The girl carried a round orange bag to school.", ["girl", "round", "orange", "school"], "r coloring and final sounds", "medium"],
  ["He found twelve clean spoons in the drawer.", ["found", "twelve", "clean", "spoons", "drawer"], "clusters", "hard"],
  ["The speaker paused briefly after each thought group.", ["speaker", "paused", "briefly", "thought", "group"], "pausing and thought groups", "medium"],
  ["A friendly clerk wrote the price on a card.", ["friendly", "clerk", "wrote", "price", "card"], "r and clusters", "medium"],
  ["Slow practice helps learners notice difficult sounds.", ["slow", "practice", "learners", "difficult", "sounds"], "metacognitive fluency", "easy"],
].map(([target_text, focus_words, speaking_target, difficulty], index) => ({
  id: index + 1,
  target_text: target_text as string,
  focus_words: focus_words as string[],
  speaking_target: speaking_target as string,
  difficulty: difficulty as string,
  model_audio_path: "",
  created_at: new Date().toISOString(),
}));

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (shouldUseDemoFallback()) {
      return demoApi<T>(path, init);
    }
    throw error;
  }
}

export function exportUrl(path: string) {
  if (!shouldUseDemoFallback()) return `${API_BASE}${path}`;
  const rows = path.startsWith("/exports/tasks") ? taskRows() : attemptRows(path);
  return csvDataUrl(rows);
}

function shouldUseDemoFallback() {
  return window.location.hostname.endsWith("github.io") || API_BASE === "demo";
}

async function demoApi<T>(path: string, init?: RequestInit): Promise<T> {
  await new Promise((resolve) => window.setTimeout(resolve, 160));
  if (path === "/tasks" && !init?.method) return getTasks() as T;
  if (path === "/tasks" && init?.method === "POST") return createTask(init) as T;
  if (path.startsWith("/tasks/") && init?.method === "PUT") return updateTask(path, init) as T;
  if (path === "/attempts/analyze" && init?.method === "POST") return analyzeAttempt(init) as T;
  if (path.startsWith("/attempts/")) return attemptsFor(path.split("/").pop() || "") as T;
  if (path === "/studies" && init?.method === "POST") return { id: 2, study_name: "New Study", description: "Browser-local demo study.", active: true } as T;
  if (path === "/studies") return [{ id: 1, study_name: "Default Speech-AI Feedback Study", description: "Browser-local demo study.", active: true }] as T;
  if (path.endsWith("/conditions")) return demoConditions() as T;
  if (path.endsWith("/assign")) return { ok: true } as T;
  if (path === "/annotations/pending") return getAttempts().slice().reverse() as T;
  if (path === "/annotations" && init?.method === "POST") return saveDemoAnnotation(init) as T;
  if (path === "/annotations/report") return [] as T;
  if (path.startsWith("/dashboard/summary")) return dashboardSummary(path) as T;
  throw new Error("Demo endpoint not implemented.");
}

function getTasks() {
  const raw = localStorage.getItem(TASK_KEY);
  if (!raw) {
    localStorage.setItem(TASK_KEY, JSON.stringify(defaultTasks));
    return defaultTasks;
  }
  return JSON.parse(raw) as Task[];
}

function demoConditions() {
  return [
    ["assessment_only", "Condition A: Assessment-only", false, false, false, false],
    ["transcript_only", "Condition B: Transcript-only", true, false, false, true],
    ["score_only", "Condition C: Score-only", true, true, false, true],
    ["explainable", "Condition D: Explainable rule-based feedback", true, true, true, true],
    ["adaptive", "Condition E: Adaptive learner-model feedback", true, true, true, true],
    ["human_validated", "Condition F: Human-validated feedback", true, true, false, true],
    ["llm_verbalized", "Condition G: LLM verbalized feedback", true, true, true, true],
  ].map(([condition_code, condition_name, show_transcript, show_score, show_diagnosis, revision_allowed], index) => ({
    id: index + 1,
    condition_code,
    condition_name,
    show_transcript,
    show_score,
    show_diagnosis,
    revision_allowed,
  }));
}

function saveDemoAnnotation(init: RequestInit) {
  const annotations = JSON.parse(localStorage.getItem(ANNOTATION_KEY) || "[]");
  const annotation = { id: annotations.length + 1, created_at: new Date().toISOString(), ...JSON.parse(String(init.body)) };
  localStorage.setItem(ANNOTATION_KEY, JSON.stringify([...annotations, annotation]));
  return annotation;
}

function saveTasks(tasks: Task[]) {
  localStorage.setItem(TASK_KEY, JSON.stringify(tasks));
}

function getAttempts() {
  return JSON.parse(localStorage.getItem(ATTEMPT_KEY) || "[]") as Attempt[];
}

function saveAttempts(attempts: Attempt[]) {
  localStorage.setItem(ATTEMPT_KEY, JSON.stringify(attempts));
}

function createTask(init: RequestInit) {
  const tasks = getTasks();
  const payload = JSON.parse(String(init.body));
  const task: Task = { id: Math.max(0, ...tasks.map((item) => item.id)) + 1, created_at: new Date().toISOString(), ...payload };
  saveTasks([...tasks, task]);
  return task;
}

function updateTask(path: string, init: RequestInit) {
  const taskId = Number(path.split("/").pop());
  const payload = JSON.parse(String(init.body));
  const tasks = getTasks();
  const updated = tasks.map((task) => (task.id === taskId ? { ...task, ...payload } : task));
  saveTasks(updated);
  return updated.find((task) => task.id === taskId);
}

function analyzeAttempt(init: RequestInit) {
  const form = init.body as FormData;
  const participantId = String(form.get("participant_id") || "sample001");
  const groupId = String(form.get("group_id") || "explainable");
  const taskId = Number(form.get("task_id") || 1);
  const task = getTasks().find((item) => item.id === taskId) || getTasks()[0];
  const transcript = String(form.get("transcript_hint") || task.target_text);
  const alignment = align(task.target_text, transcript);
  const duration = 3 + Math.max(words(transcript).length * 0.42, 1);
  const speechRate = Math.round((words(transcript).length / duration) * 60 * 100) / 100;
  const longPauses = duration > words(transcript).length * 0.8 + 3 ? 1 : 0;
  const score = scoreAttempt(alignment.word_match_score, alignment.missing_words.length, alignment.substitutions.length, speechRate, longPauses);
  const feedback = feedbackFor(groupId, score, alignment, speechRate, longPauses);
  const attempts = getAttempts();
  const previousForTask = attempts.filter((item) => item.participant_id === participantId && item.task_id === taskId);
  const firstScore = previousForTask[0]?.score ?? score;
  const attempt: Attempt = {
    id: Math.max(0, ...attempts.map((item) => item.id)) + 1,
    participant_id: participantId,
    task_id: taskId,
    group_id: groupId,
    attempt_number: previousForTask.length + 1,
    audio_path: "browser-local-demo",
    asr_transcript: transcript,
    duration_seconds: Math.round(duration * 100) / 100,
    speech_rate_wpm: speechRate,
    word_match_score: alignment.word_match_score,
    missing_words: alignment.missing_words,
    substitutions: alignment.substitutions,
    long_pause_count: longPauses,
    feedback_type: groupId === "control" ? "score_only" : "explainable",
    feedback,
    created_at: new Date().toISOString(),
    target_text: task.target_text,
    score,
    improvement: Math.round((score - firstScore) * 100) / 100,
  };
  saveAttempts([...attempts, attempt]);
  return attempt;
}

function attemptsFor(participantId: string) {
  return getAttempts().filter((attempt) => attempt.participant_id === decodeURIComponent(participantId));
}

function dashboardSummary(path: string): Summary {
  const url = new URL(path, window.location.origin);
  const group = url.searchParams.get("group") || "";
  const participant = url.searchParams.get("participant") || "";
  let attempts = getAttempts();
  if (group) attempts = attempts.filter((attempt) => attempt.group_id === group);
  if (participant) attempts = attempts.filter((attempt) => attempt.participant_id === participant);
  const participantCount = new Set(attempts.map((attempt) => attempt.participant_id)).size;
  const taskCount = new Set(attempts.map((attempt) => attempt.task_id)).size || 1;
  const missing = countItems(attempts.flatMap((attempt) => attempt.missing_words));
  const substitutions = countItems(attempts.flatMap((attempt) => attempt.substitutions.map((item) => `${item.expected} -> ${item.heard || ""}`)));
  return {
    participants: participantCount,
    attempts: attempts.length,
    average_attempts_per_task: round(attempts.length / taskCount),
    average_word_match_score: average(attempts.map((attempt) => attempt.word_match_score)),
    average_speech_rate_wpm: average(attempts.map((attempt) => attempt.speech_rate_wpm)),
    common_missing_words: missing.map(([word, count]) => ({ word, count })),
    common_substitutions: substitutions.map(([substitution, count]) => ({ substitution, count })),
    average_improvement_first_to_latest: averageImprovement(attempts),
    feedback_views: attempts.length,
    revision_events: attempts.filter((attempt) => attempt.attempt_number > 1).length,
  };
}

function words(text: string) {
  return (text.toLowerCase().match(/[a-z']+/g) || []).map((word) => word.replace(/^'|'$/g, ""));
}

function align(targetText: string, transcript: string) {
  const target = words(targetText);
  const spoken = words(transcript);
  const missing_words = target.filter((word) => !spoken.includes(word));
  const substitutions = target
    .map((word, index) => ({ expected: word, heard: spoken[index] || "" }))
    .filter((item) => item.heard && item.expected !== item.heard && !missing_words.includes(item.expected))
    .slice(0, 6);
  const matched = target.filter((word) => spoken.includes(word)).length;
  return { word_match_score: round((matched / Math.max(target.length, 1)) * 100), missing_words, substitutions };
}

function scoreAttempt(match: number, missing: number, substitutions: number, speechRate: number, pauses: number) {
  let score = match * 0.7 - missing * 4 - substitutions * 3 - pauses * 3;
  if (speechRate < 70 || speechRate > 180) score -= 8;
  return Math.max(0, Math.min(100, round(score)));
}

function feedbackFor(groupId: string, score: number, alignment: ReturnType<typeof align>, speechRate: number, pauses: number): Record<string, string | number> {
  if (groupId === "control") {
    return { overall_score: score, comment: `Your current clarity score is ${score}. Please practise again and try to read the sentence more clearly.` };
  }
  const issue = alignment.missing_words[0] || alignment.substitutions[0]?.expected || "";
  if (issue) {
    return {
      overall_score: score,
      diagnosis: `The word '${issue}' may not have been clearly recognized.`,
      explanation: "This word carries sentence meaning. If it is unclear, a listener may misunderstand the message.",
      action_guidance: `Practise '${issue}' three times, then say the full sentence again with steady rhythm.`,
      revision_instruction: `After re-recording, compare whether '${issue}' is recognized more clearly.`,
    };
  }
  if (speechRate < 70 || speechRate > 180 || pauses > 0) {
    return {
      overall_score: score,
      diagnosis: "The reading pace or pausing pattern may affect fluency.",
      explanation: "A steady pace helps listeners follow the sentence and notice key words.",
      action_guidance: "Practise the sentence in short chunks, then connect the chunks smoothly.",
      revision_instruction: "Re-record and compare the speech rate, transcript, and clarity score.",
    };
  }
  return {
    overall_score: score,
    diagnosis: "Most target words were recognized clearly in this attempt.",
    explanation: "Clear recognition suggests the main words were understandable.",
    action_guidance: "Repeat once more while keeping the same clarity and smooth rhythm.",
    revision_instruction: "Use the next attempt to check whether the clarity score remains stable or improves.",
  };
}

function average(values: number[]) {
  return values.length ? round(values.reduce((sum, value) => sum + value, 0) / values.length) : 0;
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}

function countItems(items: string[]) {
  const counts = new Map<string, number>();
  items.filter(Boolean).forEach((item) => counts.set(item, (counts.get(item) || 0) + 1));
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
}

function averageImprovement(attempts: Attempt[]) {
  const groups = new Map<string, Attempt[]>();
  attempts.forEach((attempt) => {
    const key = `${attempt.participant_id}:${attempt.task_id}`;
    groups.set(key, [...(groups.get(key) || []), attempt]);
  });
  const improvements = [...groups.values()]
    .filter((items) => items.length > 1)
    .map((items) => {
      const sorted = items.sort((a, b) => a.attempt_number - b.attempt_number);
      return sorted[sorted.length - 1].score - sorted[0].score;
    });
  return average(improvements);
}

function attemptRows(path: string) {
  const participantId = path.startsWith("/exports/participant/") ? decodeURIComponent(path.split("/").pop() || "") : "";
  const rows = participantId ? attemptsFor(participantId) : getAttempts();
  return [
    ["attempt_id", "participant_id", "group_id", "task_id", "attempt_number", "timestamp", "target_text", "transcript", "score", "duration_seconds", "speech_rate_wpm", "word_match_score", "missing_words", "substitutions", "long_pause_count", "feedback_type"],
    ...rows.map((attempt) => [attempt.id, attempt.participant_id, attempt.group_id, attempt.task_id, attempt.attempt_number, attempt.created_at, attempt.target_text, attempt.asr_transcript, attempt.score, attempt.duration_seconds, attempt.speech_rate_wpm, attempt.word_match_score, attempt.missing_words.join(" "), attempt.substitutions.map((item) => `${item.expected}->${item.heard}`).join(" "), attempt.long_pause_count, attempt.feedback_type]),
  ];
}

function taskRows() {
  return [
    ["task_id", "target_text", "difficulty", "speaking_target", "focus_words"],
    ...getTasks().map((task) => [task.id, task.target_text, task.difficulty, task.speaking_target, task.focus_words.join(" ")]),
  ];
}

function csvDataUrl(rows: Array<Array<string | number>>) {
  const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
  return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
}
