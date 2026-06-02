import { useMemo, useRef, useState } from "react";
import { Mic, Square, Upload, RotateCcw } from "lucide-react";
import { api, Attempt, Task } from "../api/client";

type Props = {
  participantId: string;
  groupId: string;
  sessionId: string;
  tasks: Task[];
  onAttempt: (attempt: Attempt) => void;
};

export function LearnerPractice({ participantId, groupId, sessionId, tasks, onAttempt }: Props) {
  const [taskId, setTaskId] = useState<number>(tasks[0]?.id || 1);
  const [recording, setRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioName, setAudioName] = useState("recording.webm");
  const [transcriptHint, setTranscriptHint] = useState("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const task = useMemo(() => tasks.find((item) => item.id === taskId) || tasks[0], [tasks, taskId]);

  async function startRecording() {
    setError("");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => chunksRef.current.push(event.data);
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      setAudioBlob(blob);
      setAudioName("recording.webm");
      stream.getTracks().forEach((track) => track.stop());
    };
    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  function onUpload(file: File | null) {
    if (!file) return;
    setAudioBlob(file);
    setAudioName(file.name);
  }

  async function submit() {
    if (!task || !audioBlob) {
      setError("Choose a task and record or upload audio first.");
      return;
    }
    setBusy(true);
    setError("");
    const data = new FormData();
    data.append("participant_id", participantId);
    data.append("group_id", groupId);
    data.append("session_id", sessionId);
    data.append("task_id", String(task.id));
    data.append("transcript_hint", transcriptHint);
    data.append("audio", audioBlob, audioName);
    try {
      const result = await api<Attempt>("/attempts/analyze", { method: "POST", body: data });
      setAttempt(result);
      onAttempt(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-grid">
      <div className="panel main-panel">
        <div className="section-head">
          <div>
            <h2>Learner Practice</h2>
            <p>Read aloud, submit audio, review feedback, then revise with another attempt.</p>
          </div>
          {attempt && <span className="pill">Attempt {attempt.attempt_number}</span>}
        </div>

        <label>
          Speaking task
          <select value={task?.id || ""} onChange={(event) => setTaskId(Number(event.target.value))}>
            {tasks.map((item) => (
              <option value={item.id} key={item.id}>
                Task {item.id}: {item.difficulty}
              </option>
            ))}
          </select>
        </label>

        {task && (
          <article className="sentence-card">
            <span>{task.speaking_target}</span>
            <h3>{task.target_text}</h3>
            <p>Focus: {task.focus_words.join(", ") || "general intelligibility"}</p>
          </article>
        )}

        <div className="record-row">
          {!recording ? (
            <button className="primary" onClick={startRecording}>
              <Mic size={18} /> Record
            </button>
          ) : (
            <button className="danger" onClick={stopRecording}>
              <Square size={18} /> Stop
            </button>
          )}
          <label className="file-button">
            <Upload size={18} />
            Upload
            <input type="file" accept="audio/*" onChange={(event) => onUpload(event.target.files?.[0] || null)} />
          </label>
          {audioBlob && <span className="status-text">Audio ready: {audioName}</span>}
        </div>

        <label>
          Mock ASR transcript hint
          <textarea
            value={transcriptHint}
            onChange={(event) => setTranscriptHint(event.target.value)}
            placeholder="Optional in mock mode. Leave blank to use the target sentence as the transcript."
          />
        </label>

        <button className="primary submit" disabled={busy} onClick={submit}>
          <RotateCcw size={18} />
          {busy ? "Analyzing..." : attempt ? "Submit revision" : "Analyze attempt"}
        </button>
        {error && <div className="alert">{error}</div>}
      </div>

      <FeedbackPanel attempt={attempt} groupId={groupId} />
    </section>
  );
}

function FeedbackPanel({ attempt, groupId }: { attempt: Attempt | null; groupId: string }) {
  if (!attempt) {
    return (
      <aside className="panel">
        <h2>Feedback</h2>
        <p className="muted">Your transcript, metrics, score, and feedback pathway will appear here after submission.</p>
      </aside>
    );
  }
  const feedback = attempt.feedback;
  return (
    <aside className="panel feedback-panel">
      <div className="score-ring">{feedback.overall_score}</div>
      <h2>Automated Feedback</h2>
      <p className="transcript">Transcript: {attempt.asr_transcript}</p>
      <div className="metrics-grid">
        <Metric label="Duration" value={`${attempt.duration_seconds}s`} />
        <Metric label="Speech rate" value={`${attempt.speech_rate_wpm} wpm`} />
        <Metric label="Word match" value={`${attempt.word_match_score}%`} />
        <Metric label="Long pauses" value={attempt.long_pause_count} />
      </div>
      {groupId === "control" ? (
        <div className="feedback-box"><strong>Comment</strong><p>{feedback.comment}</p></div>
      ) : (
        <>
          <Box title="Diagnosis" text={String(feedback.diagnosis)} />
          <Box title="Explanation" text={String(feedback.explanation)} />
          <Box title="Action Guidance" text={String(feedback.action_guidance)} />
          <Box title="Revision" text={String(feedback.revision_instruction)} />
        </>
      )}
      <p className="small-note">Automatically generated learning support, not a high-stakes assessment.</p>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function Box({ title, text }: { title: string; text: string }) {
  return <div className="feedback-box"><strong>{title}</strong><p>{text}</p></div>;
}
