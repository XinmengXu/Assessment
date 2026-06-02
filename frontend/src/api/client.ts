export const API_BASE = "/api";

export type Task = {
  id: number;
  target_text: string;
  focus_words: string[];
  speaking_target: string;
  difficulty: string;
  model_audio_path: string;
  created_at: string;
};

export type Attempt = {
  id: number;
  participant_id: string;
  task_id: number;
  group_id: string;
  attempt_number: number;
  asr_transcript: string;
  duration_seconds: number;
  speech_rate_wpm: number;
  word_match_score: number;
  missing_words: string[];
  substitutions: { expected: string; heard: string }[];
  long_pause_count: number;
  feedback_type: string;
  feedback: Record<string, string | number>;
  created_at: string;
  target_text: string;
  score: number;
  improvement: number;
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function exportUrl(path: string) {
  return `${API_BASE}${path}`;
}
