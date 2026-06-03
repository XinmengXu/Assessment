import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BarChart3,
  BookOpen,
  ClipboardCheck,
  ClipboardList,
  Database,
  Gauge,
  LogOut,
  ShieldCheck,
  Users,
} from "lucide-react";
import { api, apiAssetUrl, Attempt, BackendStatus, checkBackendHealth, exportUrl, getBackendStatus, PilotUser, Task, UserRole } from "./api/client";
import { LearnerPractice } from "./pages/LearnerPractice";
import { TaskManagement } from "./pages/TaskManagement";
import { StudyDesign } from "./pages/StudyDesign";
import "./styles.css";

type Page =
  | "practice"
  | "my-feedback"
  | "my-progress"
  | "student-list"
  | "give-feedback"
  | "class-summary"
  | "peer-tasks"
  | "submitted-reviews"
  | "human-rating"
  | "study-setup"
  | "task-bank"
  | "users-groups"
  | "data-export"
  | "system-status";

const DEFAULT_PAGE: Record<UserRole, Page> = {
  student: "practice",
  teacher: "student-list",
  peer_reviewer: "peer-tasks",
  rater: "human-rating",
  researcher_admin: "study-setup",
};

const roleNav = {
  student: [
    ["practice", BookOpen, "Practice"],
    ["my-feedback", ClipboardCheck, "My Feedback"],
    ["my-progress", BarChart3, "My Progress"],
  ],
  teacher: [
    ["student-list", Users, "Student List"],
    ["give-feedback", ClipboardCheck, "Give Feedback"],
    ["class-summary", BarChart3, "Class Summary"],
  ],
  peer_reviewer: [
    ["peer-tasks", ClipboardCheck, "Peer Review Tasks"],
    ["submitted-reviews", ClipboardList, "Submitted Reviews"],
  ],
  rater: [
    ["human-rating", ClipboardCheck, "Blinded Rating"],
  ],
  researcher_admin: [
    ["study-setup", ShieldCheck, "Study Setup"],
    ["task-bank", ClipboardList, "Task Bank"],
    ["users-groups", Users, "Users and Groups"],
    ["data-export", Database, "Data Export"],
    ["system-status", Gauge, "System Status"],
  ],
} as const;

function App() {
  const [user, setUser] = useState<PilotUser | null>(null);
  const [page, setPage] = useState<Page>("practice");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [latestAttempt, setLatestAttempt] = useState<Attempt | null>(null);
  const [selectedTeacherAttempt, setSelectedTeacherAttempt] = useState<Attempt | null>(null);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>(getBackendStatus());
  const [error, setError] = useState("");

  useEffect(() => {
    checkBackendHealth().then(setBackendStatus);
    const stored = localStorage.getItem("pilotUserCode");
    if (stored) {
      api<PilotUser>(`/me?user_code=${encodeURIComponent(stored)}`).then((nextUser) => {
        setUser(nextUser);
        setPage(DEFAULT_PAGE[nextUser.role]);
      }).catch(() => localStorage.removeItem("pilotUserCode"));
    }
    api<Task[]>("/tasks").then(setTasks).catch((err) => setError(err.message)).finally(() => setBackendStatus(getBackendStatus()));
  }, []);

  const nav = useMemo(() => (user ? roleNav[user.role] : []), [user]);

  async function login(userCode: string) {
    setError("");
    try {
      const result = await api<{ user: PilotUser }>("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_code: userCode }),
      });
      setUser(result.user);
      setPage(DEFAULT_PAGE[result.user.role]);
      localStorage.setItem("pilotUserCode", result.user.user_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  function logout() {
    localStorage.removeItem("pilotUserCode");
    setUser(null);
    setPage("practice");
  }

  if (!user) {
    return (
      <main className="login-screen">
        <BackendStatusBanner status={backendStatus} />
        <LoginPanel onLogin={login} error={error} />
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck size={28} />
          <div>
            <h1>Speech-AI Practice</h1>
            <p>Formative speaking platform</p>
          </div>
        </div>
        <div className="user-card">
          <strong>{user.display_name}</strong>
          <span>{roleLabel(user.role)}</span>
          <button onClick={logout}><LogOut size={16} /> Log out</button>
        </div>
        <nav>
          {nav.map(([id, Icon, label]) => (
            <button className={page === id ? "active" : ""} key={id} onClick={() => setPage(id as Page)}>
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <section className="privacy-note">
          <strong>Formative use only</strong>
          <p>Automatic scores are practice indicators. Teacher ratings are needed for stronger learning-outcome claims.</p>
        </section>
      </aside>

      <main>
        <BackendStatusBanner status={backendStatus} />
        {error && <div className="alert">{error}</div>}
        {page === "practice" && (
          <LearnerPractice
            participantId={user.user_code}
            groupId={user.condition_group || "G3"}
            sessionId="pilot-session"
            tasks={tasks}
            userRole={user.role}
            onAttempt={setLatestAttempt}
          />
        )}
        {page === "my-feedback" && <StudentFeedback user={user} latestAttempt={latestAttempt} />}
        {page === "my-progress" && <StudentProgress user={user} />}
        {page === "student-list" && <TeacherStudentList user={user} onReview={(attempt) => { setSelectedTeacherAttempt(attempt); setPage("give-feedback"); }} />}
        {page === "give-feedback" && <TeacherFeedbackPage user={user} selectedAttempt={selectedTeacherAttempt} onSelectAttempt={setSelectedTeacherAttempt} />}
        {page === "class-summary" && <ClassSummary user={user} />}
        {page === "peer-tasks" && <PeerReviewTasks user={user} />}
        {page === "submitted-reviews" && <SubmittedReviews user={user} />}
        {page === "human-rating" && <HumanRatingPage user={user} />}
        {page === "study-setup" && <StudyDesign />}
        {page === "task-bank" && <TaskManagement tasks={tasks} onTasks={setTasks} />}
        {page === "users-groups" && <UsersAndGroups />}
        {page === "data-export" && <DataExport />}
        {page === "system-status" && <SystemStatus />}
      </main>
    </div>
  );
}

function LoginPanel({ onLogin, error }: { onLogin: (userCode: string) => void; error: string }) {
  const [userCode, setUserCode] = useState(localStorage.getItem("pilotUserCode") || "student001");
  return (
    <section className="panel login-panel">
      <div className="section-head">
        <div>
          <h2>Speech-AI Formative Speaking Practice Platform</h2>
          <p>Enter your pilot user code. Example accounts: student001, teacher001, peer001, rater001, admin001.</p>
        </div>
      </div>
      <label>User code<input value={userCode} onChange={(event) => setUserCode(event.target.value)} /></label>
      <button className="primary submit" onClick={() => onLogin(userCode)}>Log in</button>
      {error && <div className="alert">{error}</div>}
    </section>
  );
}

function BackendStatusBanner({ status }: { status: BackendStatus }) {
  if (status.mode === "real") return <div className="status-banner real-api">Backend connected: real API mode. ASR adapter: {status.asr_adapter}. Pronunciation provider: {status.pronunciation_provider || "unknown"}</div>;
  if (status.mode === "checking") return <div className="status-banner checking">Checking backend connection at {status.api_base}</div>;
  return <div className="demo-banner">Demo mode: no real backend connected. Scores are simulated practice scores only. Audio is accepted only for interface testing. {status.reason}</div>;
}

function StudentFeedback({ user, latestAttempt }: { user: PilotUser; latestAttempt: Attempt | null }) {
  const [data, setData] = useState<{ ai_feedback: Attempt[]; teacher_feedback: Record<string, unknown>[]; peer_feedback: Record<string, unknown>[] }>({ ai_feedback: [], teacher_feedback: [], peer_feedback: [] });
  useEffect(() => { api<typeof data>(`/student/feedback?user_code=${user.user_code}`).then(setData); }, [user.user_code]);
  const attempts = latestAttempt ? [latestAttempt, ...data.ai_feedback.filter((item) => item.id !== latestAttempt.id)] : data.ai_feedback;
  return (
    <section className="stack">
      <FeedbackList title="AI-supported practice feedback" rows={attempts} />
      <SimpleRecordList title="Teacher feedback" rows={data.teacher_feedback} empty="Released teacher feedback will appear here." />
      <SimpleRecordList title="Peer feedback" rows={data.peer_feedback} empty="Peer suggestions will appear here." />
    </section>
  );
}

function StudentProgress({ user }: { user: PilotUser }) {
  const [progress, setProgress] = useState<Record<string, unknown>>({});
  useEffect(() => { api<Record<string, unknown>>(`/student/progress?user_code=${user.user_code}`).then(setProgress); }, [user.user_code]);
  return <MetricsPage title="My Progress" data={progress} />;
}

function TeacherStudentList({ user, onReview }: { user: PilotUser; onReview: (attempt: Attempt) => void }) {
  const [rows, setRows] = useState<Attempt[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<string>("");
  useEffect(() => { api<Attempt[]>(`/teacher/submissions?user_code=${user.user_code}`).then(setRows); }, [user.user_code]);
  const students = [...rows.reduce((map, attempt) => {
    const item = map.get(attempt.participant_id) || { student_id: attempt.participant_id, display_name: String((attempt as Attempt & { display_name?: string }).display_name || attempt.participant_id), completed: 0, revisions: 0, latest: attempt, attempts: [] as Attempt[] };
    item.completed += 1;
    item.revisions += attempt.attempt_number > 1 ? 1 : 0;
    item.latest = attempt;
    item.attempts.push(attempt);
    map.set(attempt.participant_id, item);
    return map;
  }, new Map<string, { student_id: string; display_name: string; completed: number; revisions: number; latest: Attempt; attempts: Attempt[] }>()).values()];
  const detail = students.find((student) => student.student_id === selectedStudent);
  if (detail) {
    const byTask = [...detail.attempts.reduce((map, attempt) => {
      const items = map.get(attempt.task_id) || [];
      map.set(attempt.task_id, [...items, attempt]);
      return map;
    }, new Map<number, Attempt[]>()).entries()];
    return (
      <section className="stack">
        <div className="panel">
          <div className="section-head"><div><h2>Student Detail</h2><p>{detail.student_id} · {detail.display_name}</p></div><button className="file-button" onClick={() => setSelectedStudent("")}>Back to Student List</button></div>
          <table>
            <thead><tr><th>Task ID</th><th>Target sentence</th><th>Attempts</th><th>Condition group</th><th>AI feedback shown</th><th>Teacher feedback status</th><th>Action</th></tr></thead>
            <tbody>{byTask.map(([taskId, attempts]) => {
              const latest = attempts[0];
              const shown = latest.show_score && latest.show_comment ? "score/comment" : latest.show_score ? "score" : latest.show_comment ? "comment" : "none";
              return (
                <tr key={taskId}>
                  <td>{taskId}</td>
                  <td>{latest.target_text}</td>
                  <td>{attempts.length}</td>
                  <td>{latest.condition_group || latest.group_id}</td>
                  <td>{shown}</td>
                  <td>not released</td>
                  <td><button className="primary" onClick={() => onReview(latest)}>Review</button></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      </section>
    );
  }
  return (
    <section className="panel">
      <h2>Student List</h2>
      <table>
        <thead><tr><th>Student ID</th><th>Display name</th><th>Class</th><th>Group</th><th>Condition group</th><th>Completed tasks</th><th>Pending feedback</th><th>Revisions</th><th>Last activity</th><th>Action</th></tr></thead>
        <tbody>{students.map((student) => (
          <tr key={student.student_id}>
            <td>{student.student_id}</td>
            <td>{student.display_name}</td>
            <td>{String((student.latest as Attempt & { class_id?: number }).class_id || user.class_id || "-")}</td>
            <td>{String((student.latest as Attempt & { user_group_id?: number }).user_group_id || "-")}</td>
            <td>{student.latest.condition_group || student.latest.group_id}</td>
            <td>{new Set(student.attempts.map((attempt) => attempt.task_id)).size}</td>
            <td>{student.attempts.filter((attempt) => (attempt.score ?? 0) < 70).length}</td>
            <td>{student.revisions}</td>
            <td>{new Date(student.latest.created_at).toLocaleString()}</td>
            <td><button className="file-button" onClick={() => setSelectedStudent(student.student_id)}>View</button></td>
          </tr>
        ))}</tbody>
      </table>
    </section>
  );
}

function TeacherFeedbackPage({ user, selectedAttempt, onSelectAttempt }: { user: PilotUser; selectedAttempt: Attempt | null; onSelectAttempt: (attempt: Attempt) => void }) {
  const [rows, setRows] = useState<Attempt[]>([]);
  useEffect(() => { api<Attempt[]>(`/teacher/submissions?user_code=${user.user_code}`).then((items) => { setRows(items); if (!selectedAttempt && items[0]) onSelectAttempt(items[0]); }); }, [user.user_code]);
  const attempt = selectedAttempt || rows[0] || null;
  if (!attempt) {
    return <section className="panel"><h2>Give Feedback</h2><p className="muted">Select a student from Student List before reviewing recordings.</p></section>;
  }
  return (
    <section className="stack">
      <div className="panel"><h2>Give Feedback</h2><p className="muted">Review one selected student attempt at a time.</p></div>
      <label>Selected attempt<select value={attempt.id} onChange={(event) => { const next = rows.find((row) => row.id === Number(event.target.value)); if (next) onSelectAttempt(next); }}>{rows.map((row) => <option value={row.id} key={row.id}>{row.participant_id} · Task {row.task_id} · Attempt {row.attempt_number}</option>)}</select></label>
      <TeacherFeedbackCard attempt={attempt} user={user} />
    </section>
  );
}

function TeacherFeedbackCard({ attempt, user }: { attempt: Attempt; user: PilotUser }) {
  const [comment, setComment] = useState("");
  const [recommendedPractice, setRecommendedPractice] = useState("");
  const [word, setWord] = useState("");
  const [sound, setSound] = useState("");
  const [observedSound, setObservedSound] = useState("");
  const [requestRerecording, setRequestRerecording] = useState(true);
  const [ratings, setRatings] = useState({ pronunciation: 3, fluency: 3, comprehensibility: 3, overall: 3 });
  const [saved, setSaved] = useState("");
  async function save(release: boolean) {
    const feedback = await api<Record<string, unknown>>("/teacher/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_user_id: user.id,
        participant_id: attempt.participant_id,
        task_id: attempt.task_id,
        attempt_id: attempt.id,
        pronunciation_rating: ratings.pronunciation,
        fluency_rating: ratings.fluency,
        comprehensibility_rating: ratings.comprehensibility,
        overall_rating: ratings.overall,
        target_word: word,
        target_phoneme: sound,
        observed_phoneme: observedSound,
        comment,
        action_guidance: `${recommendedPractice}${requestRerecording ? " Please re-record after practising." : ""}`,
        status: release ? "released" : "draft",
      }),
    });
    if (release) await api(`/teacher/feedback/${feedback.id}/release`, { method: "POST" });
    setSaved(release ? "Released to student" : "Draft saved");
  }
  return (
    <article className="panel">
      <p className="pill">Student {attempt.participant_id} · Task {attempt.task_id} · Attempt {attempt.attempt_number}</p>
      <h3>{attempt.target_text}</h3>
      <p className="muted">AI group: {attempt.condition_label || attempt.condition_group || attempt.group_id}</p>
      <TtsButtons sentence={attempt.target_text} focusWords={attempt.missing_words?.slice(0, 3) || []} />
      <audio controls src={apiAssetUrl(attempt.audio_url || `/attempts/${attempt.id}/audio`)} />
      <p className="transcript">ASR transcript: {attempt.asr_transcript || "ASR returned empty transcript"}</p>
      <div className="feedback-box"><strong>AI feedback shown to student</strong><pre>{JSON.stringify(attempt.feedback, null, 2)}</pre></div>
      <div className="metrics-grid">
        <label>Pronunciation clarity rating<input type="number" min="1" max="5" value={ratings.pronunciation} onChange={(event) => setRatings({ ...ratings, pronunciation: Number(event.target.value) })} /></label>
        <label>Fluency rating<input type="number" min="1" max="5" value={ratings.fluency} onChange={(event) => setRatings({ ...ratings, fluency: Number(event.target.value) })} /></label>
        <label>Comprehensibility rating<input type="number" min="1" max="5" value={ratings.comprehensibility} onChange={(event) => setRatings({ ...ratings, comprehensibility: Number(event.target.value) })} /></label>
        <label>Overall rating<input type="number" min="1" max="5" value={ratings.overall} onChange={(event) => setRatings({ ...ratings, overall: Number(event.target.value) })} /></label>
      </div>
      <label>Word needing attention<input value={word} onChange={(event) => setWord(event.target.value)} /></label>
      <label>Sound needing attention<input value={sound} onChange={(event) => setSound(event.target.value)} placeholder="th, r, final_t" /></label>
      <label>Observed sound optional<input value={observedSound} onChange={(event) => setObservedSound(event.target.value)} placeholder="Only if human-observed" /></label>
      <label>Written feedback<textarea value={comment} onChange={(event) => setComment(event.target.value)} /></label>
      <label>Recommended practice<textarea value={recommendedPractice} onChange={(event) => setRecommendedPractice(event.target.value)} /></label>
      <label className="check-row"><input type="checkbox" checked={requestRerecording} onChange={(event) => setRequestRerecording(event.target.checked)} /> Request re-recording</label>
      <div className="actions"><button className="file-button" onClick={() => save(false)}>Save draft</button><button className="primary" onClick={() => save(true)}>Release</button>{saved && <span className="status-text">{saved}</span>}</div>
    </article>
  );
}

function ClassSummary({ user }: { user: PilotUser }) {
  const [data, setData] = useState<Record<string, unknown>>({});
  useEffect(() => { api<Record<string, unknown>>(`/teacher/class-summary?user_code=${user.user_code}`).then(setData); }, [user.user_code]);
  return <MetricsPage title="Class Summary" data={data} />;
}

function PeerReviewTasks({ user }: { user: PilotUser }) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  useEffect(() => { api<Record<string, unknown>[]>(`/peer/review-tasks?user_code=${user.user_code}`).then(setRows); }, [user.user_code]);
  return (
    <section className="stack">
      <div className="panel"><h2>Peer Review Tasks</h2><p className="muted">Listen to the model sentence and the student recording, then submit supportive peer feedback.</p></div>
      {rows.length ? rows.map((row) => <PeerReviewCard key={String(row.id)} row={row} user={user} />) : <div className="panel"><p className="muted">No peer review tasks assigned yet.</p></div>}
    </section>
  );
}

function PeerReviewCard({ row, user }: { row: Record<string, unknown>; user: PilotUser }) {
  const attempt = row.attempt as Attempt | null;
  const [encouragement, setEncouragement] = useState("");
  const [suggestion, setSuggestion] = useState("");
  const [saved, setSaved] = useState("");
  if (!attempt) return <article className="panel">Attempt is no longer available.</article>;
  const reviewAttempt = attempt;
  async function submit() {
    await api("/peer/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assignment_id: row.id, reviewer_user_id: user.id, participant_id: reviewAttempt.participant_id, task_id: reviewAttempt.task_id, attempt_id: reviewAttempt.id, clarity_rating: 3, encouragement, suggestion }),
    });
    setSaved("Submitted");
  }
  return (
    <article className="panel">
      <h3>{attempt.target_text}</h3>
      <TtsButtons sentence={attempt.target_text} focusWords={[]} />
      <audio controls src={apiAssetUrl(attempt.audio_url || `/attempts/${attempt.id}/audio`)} />
      <label>What was clear?<textarea value={encouragement} onChange={(event) => setEncouragement(event.target.value)} /></label>
      <label>One practice suggestion<textarea value={suggestion} onChange={(event) => setSuggestion(event.target.value)} /></label>
      <button className="primary submit" onClick={submit}>Submit peer review</button>
      {saved && <span className="status-text">{saved}</span>}
    </article>
  );
}

function SubmittedReviews({ user }: { user: PilotUser }) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  useEffect(() => { api<Record<string, unknown>[]>(`/peer/submitted-reviews?user_code=${user.user_code}`).then(setRows); }, [user.user_code]);
  return <SimpleRecordList title="Submitted Reviews" rows={rows} empty="Submitted peer reviews will appear here." />;
}

function HumanRatingPage({ user }: { user: PilotUser }) {
  const [queue, setQueue] = useState<Record<string, unknown>[]>([]);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [startedAt, setStartedAt] = useState(new Date().toISOString());
  const [ratings, setRatings] = useState({ pronunciation: 3, fluency: 3, intelligibility: 3, comprehensibility: 3, task_completion: 3, overall_quality: 3, rating_confidence: 0.8 });
  const [comments, setComments] = useState("");
  const [unusable, setUnusable] = useState(false);
  const [saved, setSaved] = useState("");
  function load() {
    api<Record<string, unknown>[]>(`/human-ratings/queue?rater_id=${encodeURIComponent(user.user_code)}&include_intervention=true`).then((items) => {
      setQueue(items);
      setSelected(items[0] || null);
      setStartedAt(new Date().toISOString());
    });
  }
  useEffect(load, [user.user_code]);
  async function submit() {
    if (!selected) return;
    const duration = Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000));
    await api("/human-ratings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        attempt_id: selected.attempt_id,
        rater_id: user.user_code,
        rubric_version: "rubric_v1",
        ...ratings,
        comments,
        unusable_recording: unusable,
        rating_started_at: startedAt,
        rating_duration_seconds: duration,
      }),
    });
    setSaved("Rating submitted");
    setComments("");
    setUnusable(false);
    load();
  }
  return (
    <section className="stack">
      <div className="panel">
        <h2>Blinded Rating</h2>
        <p className="muted">Recordings are anonymized. Experimental condition and automatic scores are hidden.</p>
      </div>
      {!selected ? <div className="panel"><p className="muted">No recordings in the rating queue.</p></div> : (
        <article className="panel">
          <label>Recording<select value={String(selected.attempt_id)} onChange={(event) => { const next = queue.find((item) => String(item.attempt_id) === event.target.value) || null; setSelected(next); setStartedAt(new Date().toISOString()); }}>{queue.map((item) => <option value={String(item.attempt_id)} key={String(item.attempt_id)}>{String(item.anonymized_participant_id)} - {String(item.session_type)} - Task {String(item.task_code || item.task_id)}</option>)}</select></label>
          <p className="pill">{String(selected.anonymized_participant_id)} / {String(selected.session_type)} / Attempt {String(selected.attempt_number)}</p>
          <audio controls src={apiAssetUrl(String(selected.audio_url || ""))} />
          <div className="metrics-grid">
            {Object.entries(ratings).map(([key, value]) => (
              <label key={key}>{key.replace(/_/g, " ")}<input type="number" min={key === "rating_confidence" ? 0 : 1} max={key === "rating_confidence" ? 1 : 5} step={key === "rating_confidence" ? 0.1 : 1} value={value} onChange={(event) => setRatings({ ...ratings, [key]: Number(event.target.value) })} /></label>
            ))}
          </div>
          <label className="check-row"><input type="checkbox" checked={unusable} onChange={(event) => setUnusable(event.target.checked)} /> Flag unusable recording</label>
          <label>Optional comment<textarea value={comments} onChange={(event) => setComments(event.target.value)} /></label>
          <button className="primary submit" onClick={submit}>Submit rating</button>
          {saved && <span className="status-text">{saved}</span>}
        </article>
      )}
    </section>
  );
}

function UsersAndGroups() {
  const [users, setUsers] = useState<PilotUser[]>([]);
  const [saved, setSaved] = useState("");
  function load() { api<PilotUser[]>("/users").then(setUsers); }
  useEffect(load, []);
  async function updateGroup(user: PilotUser, conditionGroup: string) {
    await api("/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...user, condition_group: conditionGroup }),
    });
    setSaved(`Updated ${user.user_code}`);
    load();
  }
  return (
    <section className="panel">
      <div className="section-head"><h2>Users and Groups</h2><a className="button-link" href={exportUrl("/users/export")}>Export users</a></div>
      <table>
        <thead><tr><th>Student ID</th><th>Display name</th><th>Role</th><th>Class</th><th>Group</th><th>Condition group</th><th>Condition label</th><th>Edit</th></tr></thead>
        <tbody>{users.map((item) => (
          <tr key={item.id}>
            <td>{item.user_code}</td>
            <td>{item.display_name}</td>
            <td>{item.role}</td>
            <td>{item.class_id || "-"}</td>
            <td>{item.group_id || "-"}</td>
            <td>{item.condition_group || "-"}</td>
            <td>{item.condition_label || "-"}</td>
            <td>{item.role === "student" ? <select value={item.condition_group || "G3"} onChange={(event) => updateGroup(item, event.target.value)}><option>G0</option><option>G1</option><option>G2</option><option>G3</option></select> : "-"}</td>
          </tr>
        ))}</tbody>
      </table>
      {saved && <p className="status-text">{saved}</p>}
    </section>
  );
}

function DataExport() {
  const exports = ["participants", "group-assignments", "tasks", "sessions", "attempts", "pronunciation-assessment-results", "word-level-results", "phoneme-level-results", "feedback", "feedback-events", "feedback-uptake-states", "human-ratings", "questionnaire-responses", "audit-log", "analysis-ready-long", "analysis-ready-wide", "users", "classes", "groups", "tts-audio-status", "teacher-feedback", "peer-feedback", "feedback-views", "revisions", "learner-progress", "teacher-orchestration-events", "peer-review-assignments", "all"];
  return (
    <section className="panel">
      <h2>Data Export</h2>
      <div className="export-grid">{exports.map((name) => <a className="button-link" href={exportUrl(`/exports/${name}`)} key={name}>Export {name}</a>)}</div>
    </section>
  );
}

function SystemStatus() {
  const [data, setData] = useState<Record<string, unknown>>({});
  useEffect(() => { api<Record<string, unknown>>("/system/status").then(setData); }, []);
  return <MetricsPage title="System Status" data={data} />;
}

function FeedbackList({ title, rows }: { title: string; rows: Attempt[] }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {rows.length === 0 ? <p className="muted">No feedback yet.</p> : rows.map((row) => (
        <article className="feedback-box" key={row.id}>
          <strong>Task {row.task_id}: {row.score === null ? "no score" : row.score}</strong>
          <p>{row.target_text}</p>
          <p>Transcript: {row.asr_transcript || "ASR returned empty transcript"}</p>
          <p>{String(row.feedback?.comment || row.feedback?.diagnosis || "")}</p>
        </article>
      ))}
    </section>
  );
}

function SimpleRecordList({ title, rows, empty }: { title: string; rows: Record<string, unknown>[]; empty: string }) {
  return <section className="panel"><h2>{title}</h2>{rows.length ? rows.map((row, index) => <pre key={index}>{JSON.stringify(row, null, 2)}</pre>) : <p className="muted">{empty}</p>}</section>;
}

function MetricsPage({ title, data }: { title: string; data: Record<string, unknown> }) {
  return <section className="panel"><h2>{title}</h2><pre>{JSON.stringify(data, null, 2)}</pre></section>;
}

function TtsButtons({ sentence, focusWords }: { sentence: string; focusWords: string[] }) {
  function speak(text: string) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
  return <div className="actions"><button className="file-button" onClick={() => speak(sentence)}>Play model sentence</button>{focusWords.map((word) => <button className="file-button" key={word} onClick={() => speak(word)}>Play {word}</button>)}</div>;
}

function roleLabel(role: UserRole) {
  if (role === "rater") return "Blinded rater";
  return role === "peer_reviewer" ? "Peer reviewer" : role === "researcher_admin" ? "Researcher admin" : role[0].toUpperCase() + role.slice(1);
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
