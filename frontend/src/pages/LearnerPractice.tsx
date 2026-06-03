import { useMemo, useRef, useState } from "react";
import { Mic, Square, Upload, RotateCcw, Volume2 } from "lucide-react";
import { api, Attempt, getBackendStatus, isDemoMode, Task, UserRole } from "../api/client";

type Props = {
  participantId: string;
  groupId: string;
  sessionId: string;
  tasks: Task[];
  userRole?: UserRole;
  onAttempt: (attempt: Attempt) => void;
};

export function LearnerPractice({ participantId, groupId, sessionId, tasks, userRole = "student", onAttempt }: Props) {
  const [taskId, setTaskId] = useState<number>(tasks[0]?.id || 1);
  const [selectedMode, setSelectedMode] = useState(groupId || "G3");
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
    data.append("group_id", selectedMode === "teacher_feedback" || selectedMode === "peer_feedback" ? "G3" : selectedMode);
    if (selectedMode === "teacher_feedback" || selectedMode === "peer_feedback") data.append("workflow_request", selectedMode);
    data.append("session_id", sessionId);
    data.append("task_id", String(task.id));
    if (isDemoMode()) data.append("transcript_hint", transcriptHint);
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
          Practice mode
          <select value={selectedMode} onChange={(event) => setSelectedMode(event.target.value)}>
            <option value="G0">Practice</option>
            <option value="G1">Score feedback</option>
            <option value="G2">Comment feedback</option>
            <option value="G3">Score and comment feedback</option>
            <option value="teacher_feedback">Send to teacher for review</option>
            <option value="peer_feedback">Send to peer reviewer</option>
          </select>
        </label>
        <p className="small-note">{modeHelp(selectedMode)}</p>

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
            <p>Focus: {task.focus_words.join(", ") || "general intelligibility"}</p>
            <TtsControls sentence={task.target_text} focusWords={task.focus_words} ttsStatus={task.tts_status || "browser_only"} />
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
        {audioBlob && <audio controls src={URL.createObjectURL(audioBlob)} />}

        {isDemoMode() && (
          <label>
            Demo transcript hint
            <textarea
              value={transcriptHint}
              onChange={(event) => setTranscriptHint(event.target.value)}
              placeholder="Demo mode cannot analyze audio. Optional text here only simulates the workflow."
            />
          </label>
        )}

        <button className="primary submit" disabled={busy} onClick={submit}>
          <RotateCcw size={18} />
          {busy ? "Analyzing..." : attempt && task?.revision_allowed !== false ? "Submit revision" : "Analyze attempt"}
        </button>
        {error && <div className="alert">{error}</div>}
      </div>

      <div>
        <FeedbackPanel attempt={attempt} groupId={selectedMode} />
        {userRole === "researcher_admin" ? <DebugPanel attempt={attempt} audioBlob={audioBlob} audioName={audioName} /> : null}
      </div>
    </section>
  );
}

function modeHelp(mode: string) {
  if (mode === "G0") return "TTS and recording only. No AI score or comment will be shown.";
  if (mode === "G1") return "Shows the practice clarity score only.";
  if (mode === "G2") return "Shows the practice comment only.";
  if (mode === "teacher_feedback") return "Uses score and comment feedback, then flags this attempt for teacher review.";
  if (mode === "peer_feedback") return "Uses score and comment feedback, then creates a peer review task.";
  return "Shows both practice clarity score and practice comment.";
}

function TtsControls({ sentence, focusWords, ttsStatus }: { sentence: string; focusWords: string[]; ttsStatus: string }) {
  function speak(text: string) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
  return (
    <div className="actions tts-row">
      <button className="file-button" onClick={() => speak(sentence)}><Volume2 size={18} /> Play model sentence</button>
      {focusWords.map((word) => <button className="file-button" key={word} onClick={() => speak(word)}><Volume2 size={18} /> Play {word}</button>)}
      {ttsStatus === "browser_only" ? <span className="small-note">Browser-generated reference voice</span> : null}
    </div>
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
  const showScore = Boolean(feedback.show_score || attempt.show_score);
  const showComment = Boolean(feedback.show_comment || attempt.show_comment);
  return (
    <aside className="panel feedback-panel">
      {showScore || attempt.no_speech_detected ? <div className={attempt.no_speech_detected || attempt.feedback_type === "invalid_audio" ? "score-ring invalid" : "score-ring"}>
        {scoreText}
      </div> : null}
      <h2>Automated Feedback</h2>
      <p className="small-note">Practice clarity score, not a validated speaking proficiency score.</p>
      {feedback.demo_notice ? <div className="demo-inline">{String(feedback.demo_notice)}</div> : null}
      {feedback.workflow_request ? <div className="feedback-box"><strong>Review request</strong><p>{String(feedback.workflow_request_label || "This attempt has been sent for additional review.")}</p></div> : null}
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
        {showScore ? <Metric label={feedback.simulated ? "Simulated practice score" : "Practice clarity score"} value={scoreText} /> : null}
        <Metric label="Word match" value={`${attempt.word_match_score}%`} />
        <Metric label="Long pauses" value={attempt.long_pause_count} />
      </div>
      {showComment && (
        <div className="feedback-box sound-focus-box">
          <strong>Practice Comment</strong>
          <p>Word to practise: {String(feedback.word_to_practise || feedback.word_label || "focus word")}</p>
          {feedback.target_sound || feedback.sound_focus_label ? <p>Target sound: {String(feedback.target_sound || feedback.sound_focus_label)}</p> : null}
          <p>Practice suggestion: {String(feedback.practice_suggestion || feedback.action_guidance || commentText)}</p>
          <p>Revision goal: {String(feedback.revision_goal || feedback.revision_instruction || "Try to make the focus word easier to recognize.")}</p>
          {feedback.evidence_note ? <p className="small-note">{String(feedback.evidence_note)}</p> : null}
        </div>
      )}
      {attempt.asr_sanity?.warnings?.length ? (
        <div className="feedback-box warning-box"><strong>ASR Warnings</strong><p>{attempt.asr_sanity.warnings.join(", ")}</p></div>
      ) : null}
      {attempt.no_speech_detected || attempt.feedback_type === "invalid_audio" ? (
        <div className="feedback-box error-box"><strong>No Valid Speech</strong><p>{commentText}</p></div>
      ) : !showScore && !showComment ? (
        <div className="feedback-box"><strong>Practice</strong><p>Recording saved. Listen to the model audio, practise, and re-record when ready.</p></div>
      ) : !showComment ? (
        <div className="feedback-box"><strong>Score feedback</strong><p>Your practice clarity score is shown above. No diagnostic comment is shown in this group.</p></div>
      ) : (
        null
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
        <Metric label="Pronunciation provider" value={String(attempt?.assessment_provider || status.pronunciation_provider || "unknown")} />
        <Metric label="Valid audio" value={attempt ? String(attempt.valid_audio !== false) : "not submitted"} />
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
