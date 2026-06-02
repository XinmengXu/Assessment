import { useMemo, useRef, useState } from "react";
import { Mic, Square, Upload, RotateCcw } from "lucide-react";
import { api, Attempt, getBackendStatus, Task } from "../api/client";

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
                {item.task_code || `Task ${item.id}`}: {item.task_type || "practice"} - {item.difficulty}
              </option>
            ))}
          </select>
        </label>

        {task && (
          <article className="sentence-card">
            <span>{task.speaking_target}</span>
            <h3>{task.target_text}</h3>
            <p>Task type: {task.task_type || "practice"} - Revision {task.revision_allowed === false ? "not allowed" : "allowed"} - Feedback {task.feedback_allowed === false ? "hidden" : "available"}</p>
            <p>Focus: {task.focus_words.join(", ") || "general intelligibility"}</p>
            {task.issue_types?.length ? <p>Issue focus: {task.issue_types.join(", ")}</p> : null}
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
            placeholder="Optional in mock mode. Leave blank to simulate no recognized words."
          />
        </label>

        <button className="primary submit" disabled={busy} onClick={submit}>
          <RotateCcw size={18} />
          {busy ? "Analyzing..." : attempt && task?.revision_allowed !== false ? "Submit revision" : "Analyze attempt"}
        </button>
        {error && <div className="alert">{error}</div>}
      </div>

      <div>
        <FeedbackPanel attempt={attempt} groupId={groupId} />
        <DebugPanel attempt={attempt} audioBlob={audioBlob} audioName={audioName} />
      </div>
    </section>
  );
}

function FeedbackPanel({ attempt, groupId }: { attempt: Attempt | null; groupId: string }) {
  if (!attempt) {
    return (
      <aside className="panel">
        <h2>Feedback</h2>
        <p className="muted">Your transcript, metrics, practice clarity score, and feedback pathway will appear here after submission.</p>
      </aside>
    );
  }
  const feedback = attempt.feedback;
  const scoreText = String(feedback.practice_score ?? feedback.overall_score ?? "N/A");
  const commentText = String(feedback.comment ?? "");
  return (
    <aside className="panel feedback-panel">
      <div className={attempt.no_speech_detected || attempt.feedback_type === "invalid_audio" ? "score-ring invalid" : "score-ring"}>
        {scoreText}
      </div>
      <h2>Automated Feedback</h2>
      <p className="small-note">Practice clarity score, not a validated speaking proficiency score.</p>
      {feedback.demo_notice ? <div className="demo-inline">{String(feedback.demo_notice)}</div> : null}
      {attempt.asr_transcript ? (
        <p className="transcript">Transcript: {attempt.asr_transcript}</p>
      ) : attempt.feedback_type === "invalid_audio" ? (
        <p className="transcript">ASR returned empty transcript.</p>
      ) : (
        <p className="transcript">Transcript hidden by the assigned research condition.</p>
      )}
      <div className="metrics-grid">
        <Metric label="Duration" value={`${attempt.duration_seconds}s`} />
        <Metric label="Speech rate" value={`${attempt.speech_rate_wpm} wpm`} />
        <Metric label={feedback.simulated ? "Simulated practice score" : "Practice clarity score"} value={scoreText} />
        <Metric label="Word match" value={`${attempt.word_match_score}%`} />
        <Metric label="Long pauses" value={attempt.long_pause_count} />
      </div>
      {attempt.asr_sanity?.warnings?.length ? (
        <div className="feedback-box warning-box"><strong>ASR Warnings</strong><p>{attempt.asr_sanity.warnings.join(", ")}</p></div>
      ) : null}
      {attempt.no_speech_detected || attempt.feedback_type === "invalid_audio" ? (
        <div className="feedback-box error-box"><strong>No Valid Speech</strong><p>{commentText}</p></div>
      ) : groupId === "control" ? (
        <div className="feedback-box"><strong>Comment</strong><p>{commentText}</p></div>
      ) : feedback.feedback_type === "assessment_only" ? (
        <div className="feedback-box"><strong>Assessment Mode</strong><p>{commentText}</p></div>
      ) : feedback.feedback_type === "transcript_only" ? (
        <div className="feedback-box"><strong>Transcript Only</strong><p>{commentText}</p></div>
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

function DebugPanel({ attempt, audioBlob, audioName }: { attempt: Attempt | null; audioBlob: Blob | null; audioName: string }) {
  const status = getBackendStatus();
  const breakdown = attempt?.score_breakdown?.score_breakdown || attempt?.feedback?.score_breakdown || {};
  return (
    <aside className="panel debug-panel">
      <h2>Debug Panel</h2>
      <div className="metrics-grid">
        <Metric label="Uploaded file" value={audioBlob ? audioName : "none"} />
        <Metric label="File size" value={audioBlob ? `${audioBlob.size} bytes` : "0 bytes"} />
        <Metric label="Backend" value={status.backend_connected ? "connected" : "demo/local"} />
        <Metric label="ASR adapter" value={attempt?.asr_adapter || status.asr_adapter || "unknown"} />
      </div>
      <div className="feedback-box">
        <strong>ASR transcript</strong>
        <p>{attempt?.asr_transcript || "ASR returned empty transcript."}</p>
      </div>
      <div className="feedback-box">
        <strong>Invalid audio reasons</strong>
        <p>{attempt?.invalid_reasons?.length ? attempt.invalid_reasons.join(", ") : "None reported."}</p>
      </div>
      <div className="feedback-box">
        <strong>Score breakdown</strong>
        <pre>{JSON.stringify(breakdown, null, 2)}</pre>
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function Box({ title, text }: { title: string; text: string }) {
  return <div className="feedback-box"><strong>{title}</strong><p>{text}</p></div>;
}
