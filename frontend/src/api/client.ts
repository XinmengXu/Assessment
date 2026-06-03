const CONFIGURED_API_BASE = String(import.meta.env.VITE_API_BASE || "").trim();
export const API_BASE = CONFIGURED_API_BASE && CONFIGURED_API_BASE !== "demo" ? CONFIGURED_API_BASE : "/api";

export type BackendStatus = {
  mode: "checking" | "real" | "demo";
  backend_connected: boolean;
  api_base: string;
  asr_adapter: string;
  pronunciation_provider?: string;
  provider_research_usable?: boolean;
  mock_mode?: boolean;
  status?: string;
  reason?: string;
};

let backendStatus: BackendStatus =
  !CONFIGURED_API_BASE || CONFIGURED_API_BASE === "demo"
    ? {
        mode: "demo",
        backend_connected: false,
        api_base: API_BASE,
        asr_adapter: "none",
        reason: CONFIGURED_API_BASE === "demo" ? "VITE_API_BASE is set to demo." : "VITE_API_BASE is not configured.",
      }
    : { mode: "checking", backend_connected: false, api_base: API_BASE, asr_adapter: "unknown" };
let healthPromise: Promise<BackendStatus> | null = null;

export type Task = {
  id: number;
  task_code?: string;
  task_type?: string;
  target_text: string;
  issue_types?: string[];
  focus_words: string[];
  focus_phonemes?: string[];
  word_phoneme_map?: Record<string, string[]>;
  speaking_target: string;
  difficulty: string;
  model_audio_path: string;
  model_audio_source?: "tts" | "uploaded" | "missing";
  tts_sentence_audio_path?: string;
  tts_focus_word_audio_json?: Record<string, string>;
  uploaded_sentence_audio_path_optional?: string;
  uploaded_focus_word_audio_json_optional?: Record<string, string>;
  tts_voice?: string;
  tts_status?: "generated" | "pending" | "failed" | "browser_only";
  feedback_allowed?: boolean;
  revision_allowed?: boolean;
  active?: boolean;
  created_at: string;
};

export type UserRole = "student" | "teacher" | "peer_reviewer" | "rater" | "researcher_admin";

export type PilotUser = {
  id: number;
  user_code: string;
  role: UserRole;
  display_name: string;
  class_id: number;
  group_id: number;
  active: boolean;
  created_at?: string;
  condition_group?: "G0" | "G1" | "G2" | "G3";
  condition_label?: string;
};

export type Attempt = {
  id: number;
  participant_id: string;
  task_id: number;
  group_id: string;
  attempt_number: number;
  audio_path?: string;
  audio_url?: string;
  asr_adapter?: string;
  assessment_provider?: string;
  assessment_status?: string;
  pronunciation_provider?: string;
  asr_transcript: string;
  duration_seconds: number;
  speech_rate_wpm: number;
  word_match_score: number;
  practice_clarity_score?: number | null;
  pronunciation_assessment_score?: number | null;
  pronunciation_score_valid_for_research?: boolean;
  evidence_level?: string;
  missing_words: string[];
  substitutions: { expected: string; heard: string }[];
  long_pause_count: number;
  valid_audio?: boolean;
  no_speech_detected?: boolean;
  invalid_reasons?: string[];
  feedback_type: string;
  condition_group?: string;
  condition_label?: string;
  show_score?: boolean;
  show_comment?: boolean;
  score_shown?: boolean;
  comment_shown?: boolean;
  feedback_use_state?: string;
  feedback_viewed?: boolean;
  re_recorded?: boolean;
  task_type?: string;
  condition?: string;
  feedback: Record<string, unknown>;
  alignment?: Record<string, unknown>;
  asr_sanity?: { asr_valid?: boolean; warnings?: string[]; transcript_quality?: string };
  score_breakdown?: Record<string, unknown>;
  debug_info?: Record<string, unknown>;
  created_at: string;
  target_text: string;
  score: number | null;
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

type ScoreResult = {
  practice_score: number | null;
  score_breakdown: Record<string, number>;
  score_note: string;
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
  model_audio_source: "tts",
  tts_voice: "browser-default",
  tts_status: "browser_only",
  created_at: new Date().toISOString(),
}));

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const status = await checkBackendHealth();
  if (status.mode === "demo") {
    return demoApi<T>(path, init);
  }
  try {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    setDemoStatus(`Backend request failed: ${error instanceof Error ? error.message : "unknown error"}`);
    return demoApi<T>(path, init);
  }
}

export function exportUrl(path: string) {
  if (!shouldUseDemoFallback()) return `${API_BASE}${path}`;
  const rows = path.startsWith("/exports/tasks") ? taskRows() : attemptRows(path);
  return csvDataUrl(rows);
}

export function apiAssetUrl(path: string) {
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path.startsWith("/api/") ? path.slice(4) : path}`;
}

function shouldUseDemoFallback() {
  return backendStatus.mode === "demo";
}

export function isDemoMode() {
  return shouldUseDemoFallback();
}

export async function checkBackendHealth(force = false): Promise<BackendStatus> {
  if (!force && backendStatus.mode !== "checking") return backendStatus;
  if (!CONFIGURED_API_BASE || CONFIGURED_API_BASE === "demo") return backendStatus;
  if (!force && healthPromise) return healthPromise;
  healthPromise = fetch(`${API_BASE}/health`, { cache: "no-store" })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
      const health = await response.json();
      backendStatus = {
        mode: "real",
        backend_connected: true,
        api_base: API_BASE,
        status: String(health.status || "ok"),
        asr_adapter: String(health.asr_adapter || (health.mock_mode ? "mock" : "unknown")),
        pronunciation_provider: String(health.pronunciation_provider || health.provider?.provider_name || "unknown"),
        provider_research_usable: Boolean(health.provider_research_usable || health.provider?.research_usable),
        mock_mode: Boolean(health.mock_mode),
      };
      return backendStatus;
    })
    .catch((error) => {
      setDemoStatus(`Backend health check failed: ${error instanceof Error ? error.message : "unknown error"}`);
      return backendStatus;
    });
  return healthPromise;
}

export function getBackendStatus() {
  return backendStatus;
}

export function backendModeLabel() {
  if (backendStatus.mode === "real") return `Backend connected: real API mode. ASR adapter: ${backendStatus.asr_adapter}. Pronunciation provider: ${backendStatus.pronunciation_provider || "unknown"}`;
  if (backendStatus.mode === "checking") return `Checking backend at ${API_BASE}`;
  return `Demo mode: no real backend connected. ${backendStatus.reason || ""}`;
}

function setDemoStatus(reason: string) {
  backendStatus = {
    mode: "demo",
    backend_connected: false,
    api_base: API_BASE,
    asr_adapter: "none",
    reason,
  };
}

async function demoApi<T>(path: string, init?: RequestInit): Promise<T> {
  await new Promise((resolve) => window.setTimeout(resolve, 160));
  if (path === "/health") return getBackendStatus() as T;
  if (path === "/login" && init?.method === "POST") return demoLogin(init) as T;
  if (path.startsWith("/me")) return demoUserFromPath(path) as T;
  if (path === "/users" && init?.method === "POST") return demoUser() as T;
  if (path === "/users") return demoUsers() as T;
  if (path === "/classes") return [{ id: 1, class_code: "DEMO", class_name: "Demo Class", teacher_user_id_optional: 2 }] as T;
  if (path === "/groups") return [{ id: 1, group_code: "DEMO-G", class_id: 1, group_name: "Demo Group" }] as T;
  if (path.startsWith("/student/tasks")) return getTasks() as T;
  if (path.startsWith("/student/feedback")) return { ai_feedback: getAttempts(), teacher_feedback: [], peer_feedback: [] } as T;
  if (path.startsWith("/student/progress")) return { attempt_count: getAttempts().length, tasks_practiced: new Set(getAttempts().map((item) => item.task_id)).size, feedback_views: 0, revisions: 0, latest_score: null } as T;
  if (path.startsWith("/teacher/submissions") || path.startsWith("/teacher/class-review")) return { submissions: getAttempts(), needs_review: getAttempts(), recommended_action: "Demo mode cannot verify speech. Connect the backend for real review." } as T;
  if (path.startsWith("/teacher/class-summary")) return { students: 1, attempts: getAttempts().length, average_score: null, teacher_feedback_released: 0 } as T;
  if (path.startsWith("/peer/review-tasks")) return [] as T;
  if (path.startsWith("/peer/submitted-reviews")) return [] as T;
  if (path.startsWith("/system/status")) return { status: "demo", backend: getBackendStatus(), users: 4, tasks: getTasks().length, attempts: getAttempts().length, teacher_feedback: 0, peer_feedback: 0 } as T;
  if (path.includes("/generate-tts")) return { tts_status: "browser_only", message: "Browser SpeechSynthesis reference voice will be used." } as T;
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

function demoUser(): PilotUser {
  return { id: 1, user_code: "student001", role: "student", display_name: "Demo Student", class_id: 1, group_id: 1, condition_group: "G3", condition_label: "Score and comment feedback", active: true };
}

function demoUsers(): PilotUser[] {
  return [
    demoUser(),
    { id: 2, user_code: "teacher001", role: "teacher", display_name: "Demo Teacher", class_id: 1, group_id: 1, active: true },
    { id: 3, user_code: "peer001", role: "peer_reviewer", display_name: "Demo Peer Reviewer", class_id: 1, group_id: 1, active: true },
    { id: 4, user_code: "rater001", role: "rater", display_name: "Demo Rater", class_id: 1, group_id: 1, active: true },
    { id: 5, user_code: "admin001", role: "researcher_admin", display_name: "Demo Admin", class_id: 1, group_id: 1, active: true },
  ];
}

function demoLogin(init: RequestInit) {
  const body = JSON.parse(String(init.body || "{}"));
  const user = demoUsers().find((item) => item.user_code === body.user_code) || demoUser();
  return { user, token_type: "demo_user_code" };
}

function demoUserFromPath(path: string) {
  const code = new URL(path, window.location.origin).searchParams.get("user_code") || "student001";
  return demoUsers().find((item) => item.user_code === code) || demoUser();
}

function demoConditions() {
  return [
    ["G0", "G0 Practice-only", true, false, false, true],
    ["G1", "G1 Score-only feedback", true, true, false, true],
    ["G2", "G2 Comment-only feedback", true, false, true, true],
    ["G3", "G3 Score + Comment feedback", true, true, true, true],
  ].map(([condition_code, condition_name, show_transcript, show_score, show_comment, revision_allowed], index) => ({
    id: index + 1,
    condition_code,
    condition_name,
    show_transcript,
    show_score,
    show_comment,
    show_diagnosis: show_comment,
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
  const audio = form.get("audio");
  const audioFile = audio instanceof File ? audio : null;
  const participantId = String(form.get("participant_id") || "sample001");
  const groupId = normalizeDemoGroup(String(form.get("group_id") || "G3"));
  const workflowRequest = String(form.get("workflow_request") || "");
  const taskId = Number(form.get("task_id") || 1);
  const task = getTasks().find((item) => item.id === taskId) || getTasks()[0];
  const transcript = String(form.get("transcript_hint") || "");
  const alignment = align(task.target_text, transcript);
  const duration = 3 + Math.max(words(transcript).length * 0.42, 1);
  const speechRate = Math.round((words(transcript).length / duration) * 60 * 100) / 100;
  const longPauses = duration > words(transcript).length * 0.8 + 3 ? 1 : 0;
  const noSpeech = !transcript.trim();
  const scoreBreakdown = noSpeech
    ? invalidScoreBreakdown()
    : scoreBreakdownFor(alignment.word_match_score, alignment.missing_words.length, alignment.substitutions.length, speechRate, longPauses);
  const score = noSpeech ? null : scoreBreakdown.practice_score;
  const feedback = noSpeech ? invalidDemoFeedback(scoreBreakdown) : feedbackFor(groupId, score || 0, alignment, speechRate, longPauses, scoreBreakdown);
  if (workflowRequest === "teacher_feedback" || workflowRequest === "peer_feedback") {
    feedback.workflow_request = workflowRequest;
    feedback.workflow_request_label = workflowRequest === "teacher_feedback" ? "Sent to teacher for review." : "Sent to peer reviewer.";
  }
  const attempts = getAttempts();
  const previousForTask = attempts.filter((item) => item.participant_id === participantId && item.task_id === taskId);
  const firstScore = previousForTask.find((item) => item.score !== null)?.score ?? score ?? 0;
  const attempt: Attempt = {
    id: Math.max(0, ...attempts.map((item) => item.id)) + 1,
    participant_id: participantId,
    task_id: taskId,
    group_id: groupId,
    attempt_number: previousForTask.length + 1,
    audio_path: "browser-local-demo",
    asr_adapter: "demo_no_asr",
    assessment_provider: "demo_no_pronunciation_assessment",
    assessment_status: "simulated",
    pronunciation_provider: "demo_no_pronunciation_assessment",
    asr_transcript: transcript,
    duration_seconds: Math.round(duration * 100) / 100,
    speech_rate_wpm: speechRate,
    word_match_score: alignment.word_match_score,
    missing_words: alignment.missing_words,
    substitutions: alignment.substitutions,
    long_pause_count: longPauses,
    valid_audio: !noSpeech,
    no_speech_detected: noSpeech,
    invalid_reasons: noSpeech ? ["demo_mode_no_transcript_hint", "no_real_backend_connected"] : [],
    condition_group: groupId,
    condition_label: demoGroupLabel(groupId),
    feedback_type: noSpeech ? "invalid_audio" : String(feedback.feedback_type || "score_plus_comment"),
    show_score: Boolean(feedback.show_score),
    show_comment: Boolean(feedback.show_comment),
    score_shown: feedback.practice_score !== null && feedback.practice_score !== undefined,
    comment_shown: Boolean(feedback.show_comment && feedback.comment),
    feedback,
    alignment: { ...alignment, inserted_words: [] },
    asr_sanity: {
      asr_valid: !noSpeech,
      warnings: noSpeech ? ["Demo mode cannot analyze audio. Provide transcript_hint or connect a real backend."] : [],
      transcript_quality: noSpeech ? "empty" : "valid",
    },
    score_breakdown: scoreBreakdown,
    debug_info: {
      uploaded_file_name: audioFile?.name || "unknown",
      uploaded_file_size: audioFile?.size || 0,
      backend_connected: false,
      api_base: API_BASE,
    },
    created_at: new Date().toISOString(),
    target_text: task.target_text,
    score,
    improvement: noSpeech || score === null ? 0 : Math.round((score - firstScore) * 100) / 100,
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
  return scoreBreakdownFor(match, missing, substitutions, speechRate, pauses).practice_score;
}

function scoreBreakdownFor(match: number, missing: number, substitutions: number, speechRate: number, pauses: number): ScoreResult {
  const word_match_component = round(match * 0.7);
  const missing_penalty = missing * 4;
  const substitution_penalty = substitutions * 3;
  const pause_penalty = pauses * 3;
  const speech_rate_penalty = speechRate < 70 || speechRate > 180 ? 8 : 0;
  let score = word_match_component - missing_penalty - substitution_penalty - pause_penalty - speech_rate_penalty;
  return {
    practice_score: Math.max(0, Math.min(100, round(score))),
    score_breakdown: {
      word_match_component,
      missing_penalty,
      substitution_penalty,
      speech_rate_penalty,
      pause_penalty,
      invalid_audio_penalty: 0,
    },
    score_note: "This is a simulated practice indicator, not a validated proficiency score.",
  };
}

function invalidScoreBreakdown(): ScoreResult {
  return {
    practice_score: null,
    score_breakdown: {
      word_match_component: 0,
      missing_penalty: 0,
      substitution_penalty: 0,
      speech_rate_penalty: 0,
      pause_penalty: 0,
      invalid_audio_penalty: 100,
    },
    score_note: "Demo mode cannot analyze audio. Connect the FastAPI backend for real ASR.",
  };
}

function oldScoreAttempt(match: number, missing: number, substitutions: number, speechRate: number, pauses: number) {
  let score = match * 0.7 - missing * 4 - substitutions * 3 - pauses * 3;
  if (speechRate < 70 || speechRate > 180) score -= 8;
  return Math.max(0, Math.min(100, round(score)));
}

function invalidDemoFeedback(scoreBreakdown: ScoreResult = invalidScoreBreakdown()): Record<string, unknown> {
  return {
    overall_score: null,
    practice_score: null,
    score_breakdown: scoreBreakdown.score_breakdown,
    score_note: scoreBreakdown.score_note,
    no_speech_detected: true,
    valid_audio: false,
    simulated: true,
    demo_notice: "Demo mode: audio is accepted only for interface testing. No real ASR or speech analysis is running.",
    feedback_type: "invalid_audio",
    comment: "Demo mode cannot analyze audio. Provide a transcript hint for interface testing, or connect the FastAPI backend for real ASR.",
  };
}

function feedbackFor(groupId: string, score: number, alignment: ReturnType<typeof align>, speechRate: number, pauses: number, scoreBreakdown: ScoreResult = scoreBreakdownFor(alignment.word_match_score, alignment.missing_words.length, alignment.substitutions.length, speechRate, pauses)): Record<string, unknown> {
  const group = normalizeDemoGroup(groupId);
  const issue = alignment.missing_words[0] || alignment.substitutions[0]?.expected || "";
  const word = issue || "focus word";
  const comment = issue
    ? `Practise '${word}', then read the phrase, then read the full sentence again.`
    : speechRate < 70 || speechRate > 180 || pauses > 0
      ? "Practise the sentence in short chunks, then connect the chunks smoothly."
      : "Listen to the model audio, repeat the focus words, then re-record the sentence.";
  const showScore = group === "G1" || group === "G3";
  const showComment = group === "G2" || group === "G3";
  return {
    condition_group: group,
    condition_label: demoGroupLabel(group),
    feedback_type: group === "G0" ? "practice_only" : group === "G1" ? "score_only" : group === "G2" ? "comment_only" : "score_plus_comment",
    show_score: showScore,
    show_comment: showComment,
    overall_score: showScore ? score : null,
    practice_score: showScore ? score : null,
    score_breakdown: scoreBreakdown.score_breakdown,
    score_note: scoreBreakdown.score_note,
    score_hidden: !showScore,
    comment_hidden: !showComment,
    simulated: true,
    score_label: "simulated practice score",
    demo_notice: "Demo mode: no real audio analysis is running.",
    word_to_practise: word,
    target_sound: "",
    practice_suggestion: comment,
    revision_goal: issue ? `Try to make '${word}' clearer in your next recording.` : "Try to make the focus word easier to recognize.",
    comment: showComment ? comment : "",
  };
}

function normalizeDemoGroup(value: string) {
  const key = value.toUpperCase();
  if (["G0", "PRACTICE_ONLY", "PRACTICE", "ASSESSMENT_ONLY"].includes(key)) return "G0";
  if (["G1", "SCORE_ONLY", "CONTROL"].includes(key)) return "G1";
  if (["G2", "COMMENT_ONLY", "TRANSCRIPT_ONLY"].includes(key)) return "G2";
  return "G3";
}

function demoGroupLabel(group: string) {
  return group === "G0" ? "Practice" : group === "G1" ? "Score feedback" : group === "G2" ? "Comment feedback" : "Score and comment feedback";
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
      return (sorted[sorted.length - 1].score ?? 0) - (sorted[0].score ?? 0);
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

function csvDataUrl(rows: Array<Array<string | number | null>>) {
  const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
  return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
}
