import { useEffect, useState } from "react";
import { api, Attempt, exportUrl } from "../api/client";
import { Download, Save } from "lucide-react";

type PendingFeedback = { id: number; attempt_id: number; participant_id: string; diagnosis: string; validation_status: string; released_to_learner: boolean };

export function AnnotationReview() {
  const [pending, setPending] = useState<Attempt[]>([]);
  const [pendingFeedback, setPendingFeedback] = useState<PendingFeedback[]>([]);
  const [selected, setSelected] = useState<Attempt | null>(null);
  const [form, setForm] = useState({
    annotator_id: "annotator01",
    transcript_acceptable: true,
    human_missing_words: "",
    human_unclear_words: "",
    human_substitutions: "",
    human_long_pause_count: 0,
    pronunciation_rating: 0,
    fluency_rating: 0,
    comprehensibility_rating: 0,
    feedback_appropriate: true,
    notes: "",
  });

  function load() {
    api<Attempt[]>("/annotations/pending").then((items) => {
      setPending(items);
      setSelected((current) => current || items[0] || null);
    });
    api<PendingFeedback[]>("/feedback/pending-review").then(setPendingFeedback);
  }

  useEffect(load, []);

  async function save() {
    if (!selected) return;
    await api("/annotations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        attempt_id: selected.id,
        human_missing_words: split(form.human_missing_words),
        human_unclear_words: split(form.human_unclear_words),
        human_substitutions: split(form.human_substitutions).map((item) => ({ expected: item, heard: "" })),
      }),
    });
    setSelected(null);
    load();
  }

  async function approveRelease(item: PendingFeedback) {
    await api(`/feedback/${item.id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await api(`/feedback/${item.id}/release`, { method: "POST" });
    load();
  }

  async function reject(item: PendingFeedback) {
    await api(`/feedback/${item.id}/reject`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Rejected in annotation review." }) });
    load();
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="section-head">
          <div><h2>Annotation Review</h2><p>Validate automatic transcript, diagnosis, and feedback quality.</p></div>
          <a className="button-link" href={exportUrl("/exports/annotations")}><Download size={18} /> CSV</a>
        </div>
        <div className="task-list">
          {pending.map((attempt) => (
            <button key={attempt.id} onClick={() => setSelected(attempt)}>
              <strong>Attempt {attempt.id} · {attempt.participant_id}</strong>
              <span>{attempt.target_text}</span>
              <small>{attempt.feedback_type} · score {attempt.score}</small>
            </button>
          ))}
        </div>
      </div>
      <div className="panel">
        {selected ? (
          <>
            <h2>Human Validation</h2>
            <p className="transcript">Target: {selected.target_text}</p>
            <p className="transcript">ASR: {selected.asr_transcript || "hidden"}</p>
            <div className="feedback-box"><strong>Automatic diagnosis</strong><p>{String(selected.feedback.diagnosis || selected.feedback.comment || "No diagnosis shown")}</p></div>
            <label className="check-row"><input type="checkbox" checked={form.transcript_acceptable} onChange={(event) => setForm({ ...form, transcript_acceptable: event.target.checked })} /> Transcript acceptable</label>
            <label>Missing words<input value={form.human_missing_words} onChange={(event) => setForm({ ...form, human_missing_words: event.target.value })} /></label>
            <label>Unclear words<input value={form.human_unclear_words} onChange={(event) => setForm({ ...form, human_unclear_words: event.target.value })} /></label>
            <label>Substituted words<input value={form.human_substitutions} onChange={(event) => setForm({ ...form, human_substitutions: event.target.value })} /></label>
            <label>Long pauses<input type="number" value={form.human_long_pause_count} onChange={(event) => setForm({ ...form, human_long_pause_count: Number(event.target.value) })} /></label>
            <label>Pronunciation rating<input type="number" min="0" max="100" value={form.pronunciation_rating} onChange={(event) => setForm({ ...form, pronunciation_rating: Number(event.target.value) })} /></label>
            <label>Fluency rating<input type="number" min="0" max="100" value={form.fluency_rating} onChange={(event) => setForm({ ...form, fluency_rating: Number(event.target.value) })} /></label>
            <label>Comprehensibility rating<input type="number" min="0" max="100" value={form.comprehensibility_rating} onChange={(event) => setForm({ ...form, comprehensibility_rating: Number(event.target.value) })} /></label>
            <label className="check-row"><input type="checkbox" checked={form.feedback_appropriate} onChange={(event) => setForm({ ...form, feedback_appropriate: event.target.checked })} /> Feedback appropriate</label>
            <label>Notes<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></label>
            <button className="primary submit" onClick={save}><Save size={18} /> Save annotation</button>
          </>
        ) : (
          <p className="muted">No pending attempts yet.</p>
        )}
      </div>
      <div className="panel">
        <h2>Pending Feedback Release</h2>
        <div className="task-list">
          {pendingFeedback.map((item) => (
            <button key={item.id}>
              <strong>Feedback {item.id} - Attempt {item.attempt_id}</strong>
              <span>{item.diagnosis || "Draft feedback pending review"}</span>
              <small>{item.validation_status} - released {String(item.released_to_learner)}</small>
              <span className="actions"><button className="primary" onClick={() => approveRelease(item)}>Approve + release</button><button className="danger" onClick={() => reject(item)}>Reject</button></span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function split(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}
