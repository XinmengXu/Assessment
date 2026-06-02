import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { BarChart3, BookOpen, ClipboardCheck, ClipboardList, FlaskConical, History, ShieldCheck } from "lucide-react";
import { api, Attempt, isDemoMode, Task } from "./api/client";
import { LearnerPractice } from "./pages/LearnerPractice";
import { AttemptHistory } from "./pages/AttemptHistory";
import { Dashboard } from "./pages/Dashboard";
import { TaskManagement } from "./pages/TaskManagement";
import { AnnotationReview } from "./pages/AnnotationReview";
import { StudyDesign } from "./pages/StudyDesign";
import "./styles.css";

type Page = "practice" | "history" | "dashboard" | "tasks" | "annotations" | "study";

function App() {
  const [page, setPage] = useState<Page>("practice");
  const [participantId, setParticipantId] = useState(localStorage.getItem("participantId") || "sample001");
  const [groupId, setGroupId] = useState(localStorage.getItem("groupId") || "explainable");
  const [sessionId, setSessionId] = useState(localStorage.getItem("sessionId") || "pilot-session");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [latestAttempt, setLatestAttempt] = useState<Attempt | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Task[]>("/tasks")
      .then(setTasks)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    localStorage.setItem("participantId", participantId);
    localStorage.setItem("groupId", groupId);
    localStorage.setItem("sessionId", sessionId);
  }, [participantId, groupId, sessionId]);

  const nav = useMemo(
    () => [
      ["practice", BookOpen, "Practice"],
      ["history", History, "History"],
      ["dashboard", BarChart3, "Dashboard"],
      ["tasks", ClipboardList, "Tasks"],
      ["annotations", ClipboardCheck, "Annotations"],
      ["study", FlaskConical, "Study"],
    ] as const,
    [],
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck size={28} />
          <div>
            <h1>Speech Feedback Study</h1>
            <p>Explainable research prototype</p>
          </div>
        </div>
        <nav>
          {nav.map(([id, Icon, label]) => (
            <button className={page === id ? "active" : ""} key={id} onClick={() => setPage(id)}>
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <section className="privacy-note">
          <strong>Privacy note</strong>
          <p>Recordings are stored locally. Use assigned IDs, not real names. Feedback supports learning and research; it is not a high-stakes assessment.</p>
        </section>
      </aside>

      <main>
        {isDemoMode() && (
          <div className="demo-banner">
            Demo mode: audio is not analyzed here. This page only simulates the research workflow. Run the FastAPI backend for real speech analysis.
          </div>
        )}
        <header className="topbar">
          <label>
            Participant ID
            <input value={participantId} onChange={(event) => setParticipantId(event.target.value)} />
          </label>
          <label>
            Condition
            <select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
              <option value="assessment_only">A assessment-only</option>
              <option value="transcript_only">B transcript-only</option>
              <option value="score_only">C score-only</option>
              <option value="explainable">explainable</option>
              <option value="adaptive">E adaptive</option>
              <option value="human_validated">F human-validated</option>
              <option value="llm_verbalized">G LLM verbalized</option>
            </select>
          </label>
          <label>
            Session
            <input value={sessionId} onChange={(event) => setSessionId(event.target.value)} />
          </label>
        </header>
        {error && <div className="alert">{error}</div>}
        {page === "practice" && (
          <LearnerPractice
            participantId={participantId}
            groupId={groupId}
            sessionId={sessionId}
            tasks={tasks}
            onAttempt={setLatestAttempt}
          />
        )}
        {page === "history" && <AttemptHistory participantId={participantId} latestAttempt={latestAttempt} />}
        {page === "dashboard" && <Dashboard />}
        {page === "tasks" && <TaskManagement tasks={tasks} onTasks={setTasks} />}
        {page === "annotations" && <AnnotationReview />}
        {page === "study" && <StudyDesign />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
