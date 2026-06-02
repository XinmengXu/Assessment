import { useEffect, useState } from "react";
import { api, exportUrl, Task } from "../api/client";
import { Download, Plus, Shuffle, Upload } from "lucide-react";

type Study = { id: number; study_name: string; description: string; active: boolean };
type Condition = {
  id: number;
  condition_code: string;
  condition_name: string;
  friendly_label?: string;
  show_score: boolean;
  show_comment: boolean;
  show_word_focus?: boolean;
  show_sound_focus?: boolean;
  revision_allowed: boolean;
  enable_teacher_feedback?: boolean;
  enable_peer_feedback?: boolean;
};
type Preview = { condition_group: string; condition_label: string; target_text: string; feedback: Record<string, unknown> };

const GROUP_DETAILS: Record<string, string[]> = {
  G0: ["TTS model pronunciation", "Recording and re-recording", "No score", "No comment"],
  G1: ["TTS model pronunciation", "Practice clarity score", "No diagnostic comment"],
  G2: ["TTS model pronunciation", "Diagnostic/practice comment", "No score"],
  G3: ["TTS model pronunciation", "Practice clarity score", "Diagnostic/practice comment"],
};

export function StudyDesign() {
  const [studies, setStudies] = useState<Study[]>([]);
  const [conditions, setConditions] = useState<Condition[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [participantId, setParticipantId] = useState("");
  const [condition, setCondition] = useState("G3");
  const [teacherEnabled, setTeacherEnabled] = useState(false);
  const [peerEnabled, setPeerEnabled] = useState(false);
  const [importResult, setImportResult] = useState<{ imported?: number; errors?: { row: number; reason: string }[] } | null>(null);
  const [previewGroup, setPreviewGroup] = useState("G3");
  const [previewTask, setPreviewTask] = useState(1);
  const [previewTranscript, setPreviewTranscript] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);

  function load() {
    api<Study[]>("/studies").then(setStudies);
    api<Condition[]>("/studies/1/conditions").then((rows) => {
      setConditions(rows);
      setTeacherEnabled(Boolean(rows[0]?.enable_teacher_feedback));
      setPeerEnabled(Boolean(rows[0]?.enable_peer_feedback));
    });
    api<Task[]>("/tasks").then((rows) => {
      setTasks(rows);
      setPreviewTask(rows[0]?.id || 1);
      setPreviewTranscript(rows[0]?.target_text || "");
    });
  }

  useEffect(load, []);

  async function createStudy() {
    await api<Study>("/studies", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ study_name: "Four-Group Feedback Information Study", description: "G0/G1/G2/G3 controlled read-aloud practice experiment." }) });
    load();
  }

  async function activateDesign() {
    await api("/studies/1/activate-four-group-design", { method: "POST" });
    load();
  }

  async function saveWorkflowSettings(nextTeacher = teacherEnabled, nextPeer = peerEnabled) {
    await api("/studies/1/workflow-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enable_teacher_feedback: nextTeacher, enable_peer_feedback: nextPeer }),
    });
    load();
  }

  async function assign() {
    if (!participantId) return;
    await api("/studies/1/assign", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ participant_id: participantId, condition }) });
    await api("/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_code: participantId, role: "student", display_name: participantId, condition_group: condition }) });
    setParticipantId("");
  }

  async function importAssignments(file: File | null) {
    if (!file) return;
    const data = new FormData();
    data.append("file", file);
    const result = await api<{ imported: number; errors: { row: number; reason: string }[] }>("/users/import", { method: "POST", body: data });
    setImportResult(result);
    load();
  }

  async function runPreview(group = previewGroup) {
    const result = await api<Preview>("/studies/1/feedback-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: previewTask, transcript: previewTranscript, condition_group: group }),
    });
    setPreview(result);
  }

  return (
    <section className="stack">
      <div className="panel">
        <div className="section-head">
          <div><h2>Study Setup</h2><p>Configure the formal G0/G1/G2/G3 feedback-information experiment.</p></div>
          <a className="button-link" href={exportUrl("/users/export")}><Download size={18} /> Export assignments</a>
        </div>
        <div className="actions">
          <button className="primary" onClick={createStudy}><Plus size={18} /> Create study</button>
          <button className="file-button" onClick={activateDesign}>Activate four-group design</button>
        </div>
        <div className="task-list">
          {studies.map((study) => (
            <button key={study.id}>
              <strong>{study.study_name}</strong>
              <span>{study.description}</span>
              <small>{study.active ? "active" : "inactive"}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Feedback Information Comparison Design</h2>
        <div className="condition-grid">
          {conditions.map((item) => (
            <article className="feedback-box" key={item.condition_code}>
              <strong>{item.condition_code} {item.friendly_label || item.condition_name}</strong>
              <p>{item.condition_name}</p>
              <ul>{(GROUP_DETAILS[item.condition_code] || []).map((detail) => <li key={detail}>{detail}</li>)}</ul>
              <p>Score shown: {item.show_score ? "yes" : "no"}</p>
              <p>Comment shown: {item.show_comment ? "yes" : "no"}</p>
              <p>Revision allowed: {item.revision_allowed ? "yes" : "no"}</p>
              <button className="file-button" onClick={() => { setPreviewGroup(item.condition_code); runPreview(item.condition_code); }}>Preview</button>
            </article>
          ))}
        </div>
      </div>

      <div className="page-grid">
        <div className="panel">
          <h2>Assign Students</h2>
          <div className="filters">
            <label>Student ID<input value={participantId} onChange={(event) => setParticipantId(event.target.value)} placeholder="s001" /></label>
            <label>Condition group<select value={condition} onChange={(event) => setCondition(event.target.value)}>{conditions.map((item) => <option key={item.id} value={item.condition_code}>{item.condition_code} - {item.friendly_label}</option>)}</select></label>
            <button className="primary" onClick={assign}><Shuffle size={18} /> Assign</button>
          </div>
          <p className="small-note">CSV format: user_code, role, display_name, class_id, group_id, condition_group</p>
          <label className="file-button"><Upload size={18} /> Bulk import assignments<input type="file" accept=".csv,text/csv" onChange={(event) => importAssignments(event.target.files?.[0] || null)} /></label>
          {importResult ? <div className="feedback-box"><strong>Import result</strong><p>Imported: {importResult.imported || 0}</p>{(importResult.errors || []).map((error) => <p key={`${error.row}-${error.reason}`}>Row {error.row}: {error.reason}</p>)}</div> : null}
        </div>

        <div className="panel">
          <h2>Optional Workflows</h2>
          <label className="check-row"><input type="checkbox" checked={teacherEnabled} onChange={(event) => { setTeacherEnabled(event.target.checked); saveWorkflowSettings(event.target.checked, peerEnabled); }} /> Enable teacher feedback</label>
          <label className="check-row"><input type="checkbox" checked={peerEnabled} onChange={(event) => { setPeerEnabled(event.target.checked); saveWorkflowSettings(teacherEnabled, event.target.checked); }} /> Enable peer evaluation</label>
          <p className="small-note">Teacher and peer feedback are optional workflows. They are not part of G0/G1/G2/G3 condition definitions.</p>
        </div>
      </div>

      <div className="panel">
        <h2>Preview student feedback by group</h2>
        <div className="filters">
          <label>Task<select value={previewTask} onChange={(event) => setPreviewTask(Number(event.target.value))}>{tasks.map((task) => <option key={task.id} value={task.id}>Task {task.id}: {task.target_text.slice(0, 54)}</option>)}</select></label>
          <label>Group<select value={previewGroup} onChange={(event) => setPreviewGroup(event.target.value)}>{conditions.map((item) => <option key={item.id} value={item.condition_code}>{item.condition_code} - {item.friendly_label}</option>)}</select></label>
        </div>
        <label>Simulated transcript<textarea value={previewTranscript} onChange={(event) => setPreviewTranscript(event.target.value)} /></label>
        <button className="primary submit" onClick={() => runPreview()}>Preview selected group</button>
        {preview ? <PreviewPanel preview={preview} /> : null}
      </div>
    </section>
  );
}

function PreviewPanel({ preview }: { preview: Preview }) {
  const feedback = preview.feedback;
  const showScore = Boolean(feedback.show_score);
  const showComment = Boolean(feedback.show_comment);
  return (
    <div className="feedback-box">
      <strong>{preview.condition_group}: {preview.condition_label}</strong>
      <p>{preview.target_text}</p>
      {showScore ? <p>Practice clarity score: {String(feedback.practice_score ?? "N/A")}</p> : <p>No score shown.</p>}
      {showComment ? (
        <>
          <p>Word to practise: {String(feedback.word_to_practise || "focus word")}</p>
          {feedback.target_sound ? <p>Target sound: {String(feedback.target_sound)}</p> : null}
          <p>Practice suggestion: {String(feedback.practice_suggestion || feedback.comment || "")}</p>
          <p>Revision goal: {String(feedback.revision_goal || "")}</p>
        </>
      ) : <p>No diagnostic/practice comment shown.</p>}
    </div>
  );
}
