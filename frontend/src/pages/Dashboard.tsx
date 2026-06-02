import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { api, exportUrl } from "../api/client";

type Summary = {
  participants: number;
  tasks: number;
  attempts: number;
  completion_rate_by_condition?: { condition: string; attempts: number; average_score: number; feedback_view_rate: number; re_recording_rate: number }[];
  average_attempts_per_task: number;
  average_word_match_score: number;
  average_speech_rate_wpm: number;
  common_missing_words: { word: string; count: number }[];
  common_issue_types?: { issue_type: string; count: number }[];
  common_substitutions: { substitution: string; count: number }[];
  feedback_policy_trigger_distribution?: { feedback_type: string; count: number }[];
  average_improvement_first_to_latest: number;
  feedback_views: number;
  revision_events: number;
};

type Health = {
  status: string;
  mock_mode: boolean;
  asr_adapter: string;
  whisper_model_size?: string;
  whisper_device?: string;
  app_version?: string;
};

export function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [group, setGroup] = useState("");
  const [participant, setParticipant] = useState("");

  function load() {
    const params = new URLSearchParams();
    if (group) params.set("group", group);
    if (participant) params.set("participant", participant);
    api<Summary>(`/dashboard/summary?${params}`).then(setSummary);
    api<Health>("/health").then(setHealth).catch(() => setHealth(null));
  }

  useEffect(load, []);

  return (
    <section className="panel wide">
      <div className="section-head">
        <div>
          <h2>Researcher Dashboard</h2>
          <p>Aggregate statistics for outcome and process analysis.</p>
        </div>
        <div className="actions">
          <a className="button-link" href={exportUrl("/exports/full")}><Download size={18} /> Full CSV</a>
          <a className="button-link" href={exportUrl("/exports/participants")}><Download size={18} /> Participants</a>
          <a className="button-link" href={exportUrl("/exports/attempts")}><Download size={18} /> Attempts</a>
          <a className="button-link" href={exportUrl("/exports/feedback")}><Download size={18} /> Feedback</a>
          <a className="button-link" href={exportUrl("/exports/revisions")}><Download size={18} /> Revisions</a>
          <a className="button-link" href={exportUrl("/exports/learner-states")}><Download size={18} /> States</a>
          <a className="button-link" href={exportUrl("/exports/annotations")}><Download size={18} /> Annotations</a>
        </div>
      </div>
      <div className="filters">
        <label>Group<select value={group} onChange={(event) => setGroup(event.target.value)}><option value="">All</option><option value="control">control</option><option value="explainable">explainable</option></select></label>
        <label>Participant<input value={participant} onChange={(event) => setParticipant(event.target.value)} placeholder="optional" /></label>
        <button className="primary" onClick={load}><RefreshCw size={18} /> Refresh</button>
      </div>
      {summary && (
        <>
          {health && (
            <div className={health.mock_mode ? "feedback-box warning-box" : "feedback-box"}>
              <strong>Backend Status</strong>
              <p>{health.status} - ASR: {health.asr_adapter}{health.whisper_model_size ? ` (${health.whisper_model_size}, ${health.whisper_device})` : ""}</p>
            </div>
          )}
          <div className="stats-grid">
            <Stat label="Participants" value={summary.participants} />
            <Stat label="Tasks" value={summary.tasks} />
            <Stat label="Attempts" value={summary.attempts} />
            <Stat label="Attempts/task" value={summary.average_attempts_per_task} />
            <Stat label="Word match" value={`${summary.average_word_match_score}%`} />
            <Stat label="Speech rate" value={`${summary.average_speech_rate_wpm} wpm`} />
            <Stat label="Avg improvement" value={summary.average_improvement_first_to_latest} />
            <Stat label="Feedback views" value={summary.feedback_views} />
            <Stat label="Revisions" value={summary.revision_events} />
          </div>
          <div className="two-col">
            <List title="Common Missing Words" items={summary.common_missing_words.map((item) => `${item.word}: ${item.count}`)} />
            <List title="Common Issue Types" items={(summary.common_issue_types || []).map((item) => `${item.issue_type}: ${item.count}`)} />
            <List title="Feedback Policy Triggers" items={(summary.feedback_policy_trigger_distribution || []).map((item) => `${item.feedback_type}: ${item.count}`)} />
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Condition</th><th>Attempts</th><th>Avg score</th><th>Feedback view rate</th><th>Re-recording rate</th></tr></thead>
              <tbody>{(summary.completion_rate_by_condition || []).map((row) => <tr key={row.condition}><td>{row.condition}</td><td>{row.attempts}</td><td>{row.average_score}</td><td>{row.feedback_view_rate}</td><td>{row.re_recording_rate}</td></tr>)}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return <div className="stat"><span>{label}</span><strong>{value}</strong></div>;
}

function List({ title, items }: { title: string; items: string[] }) {
  return <div className="feedback-box"><strong>{title}</strong>{items.length ? items.map((item) => <p key={item}>{item}</p>) : <p>No data yet.</p>}</div>;
}
