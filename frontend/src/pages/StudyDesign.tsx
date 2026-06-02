import { useEffect, useState } from "react";
import { api, exportUrl } from "../api/client";
import { Download, Plus, Shuffle } from "lucide-react";

type Study = { id: number; study_name: string; description: string; active: boolean };
type Condition = { id: number; condition_code: string; condition_name: string; show_transcript: boolean; show_score: boolean; show_diagnosis: boolean; revision_allowed: boolean };

export function StudyDesign() {
  const [studies, setStudies] = useState<Study[]>([]);
  const [conditions, setConditions] = useState<Condition[]>([]);
  const [participantId, setParticipantId] = useState("");
  const [condition, setCondition] = useState("explainable");

  function load() {
    api<Study[]>("/studies").then(setStudies);
    api<Condition[]>("/studies/1/conditions").then(setConditions);
  }

  useEffect(load, []);

  async function createStudy() {
    await api<Study>("/studies", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ study_name: "New Speech Feedback Study", description: "Configured from the study design page." }) });
    load();
  }

  async function assign() {
    if (!participantId) return;
    await api("/studies/1/assign", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ participant_id: participantId, condition }) });
    setParticipantId("");
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="section-head">
          <div><h2>Study Design</h2><p>Configure studies, conditions, and participant assignment.</p></div>
          <a className="button-link" href={exportUrl("/exports/study-design")}><Download size={18} /> Export</a>
        </div>
        <button className="primary" onClick={createStudy}><Plus size={18} /> Create study</button>
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
        <h2>Default Conditions A-G</h2>
        <div className="task-list">
          {conditions.map((item) => (
            <button key={item.id}>
              <strong>{item.condition_name}</strong>
              <span>Transcript {String(item.show_transcript)} · Score {String(item.show_score)} · Diagnosis {String(item.show_diagnosis)}</span>
              <small>Revision {item.revision_allowed ? "allowed" : "blocked"}</small>
            </button>
          ))}
        </div>
        <div className="filters">
          <label>Participant<input value={participantId} onChange={(event) => setParticipantId(event.target.value)} placeholder="p001" /></label>
          <label>Condition<select value={condition} onChange={(event) => setCondition(event.target.value)}>{conditions.map((item) => <option key={item.id} value={item.condition_code}>{item.condition_code}</option>)}</select></label>
          <button className="primary" onClick={assign}><Shuffle size={18} /> Assign</button>
        </div>
      </div>
    </section>
  );
}
