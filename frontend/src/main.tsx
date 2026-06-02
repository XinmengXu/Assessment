import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { BarChart3, BookOpen, ClipboardList, History, ShieldCheck } from "lucide-react";
import { api, Attempt, Task } from "./api/client";
import { LearnerPractice } from "./pages/LearnerPractice";
import { AttemptHistory } from "./pages/AttemptHistory";
import { Dashboard } from "./pages/Dashboard";
import { TaskManagement } from "./pages/TaskManagement";
import "./styles.css";

type Page = "practice" | "history" | "dashboard" | "tasks";

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
        <header className="topbar">
          <label>
            Participant ID
            <input value={participantId} onChange={(event) => setParticipantId(event.target.value)} />
          </label>
          <label>
            Group
            <select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
              <option value="explainable">explainable</option>
              <option value="control">control</option>
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
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
