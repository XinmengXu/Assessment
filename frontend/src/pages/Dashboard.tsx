import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { api, exportUrl } from "../api/client";

type Summary = {
  participants: number;
  attempts: number;
  average_attempts_per_task: number;
  average_word_match_score: number;
  average_speech_rate_wpm: number;
  common_missing_words: { word: string; count: number }[];
  common_substitutions: { substitution: string; count: number }[];
  average_improvement_first_to_latest: number;
  feedback_views: number;
  revision_events: number;
};

export function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [group, setGroup] = useState("");
  const [participant, setParticipant] = useState("");

  function load() {
    const params = new URLSearchParams();
    if (group) params.set("group", group);
    if (participant) params.set("participant", participant);
    api<Summary>(`/dashboard/summary?${params}`).then(setSummary);
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
          <a className="button-link" href={exportUrl("/exports/tasks")}><Download size={18} /> Tasks CSV</a>
        </div>
      </div>
      <div className="filters">
        <label>Group<select value={group} onChange={(event) => setGroup(event.target.value)}><option value="">All</option><option value="control">control</option><option value="explainable">explainable</option></select></label>
        <label>Participant<input value={participant} onChange={(event) => setParticipant(event.target.value)} placeholder="optional" /></label>
        <button className="primary" onClick={load}><RefreshCw size={18} /> Refresh</button>
      </div>
      {summary && (
        <>
          <div className="stats-grid">
            <Stat label="Participants" value={summary.participants} />
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
            <List title="Common Substitutions" items={summary.common_substitutions.map((item) => `${item.substitution}: ${item.count}`)} />
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
