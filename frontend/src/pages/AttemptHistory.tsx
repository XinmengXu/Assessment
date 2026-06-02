import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api, Attempt, exportUrl } from "../api/client";

export function AttemptHistory({ participantId, latestAttempt }: { participantId: string; latestAttempt: Attempt | null }) {
  const [attempts, setAttempts] = useState<Attempt[]>([]);

  useEffect(() => {
    if (!participantId) return;
    api<Attempt[]>(`/attempts/${participantId}`).then(setAttempts).catch(() => setAttempts([]));
  }, [participantId, latestAttempt]);

  return (
    <section className="panel wide">
      <div className="section-head">
        <div>
          <h2>Attempt History</h2>
          <p>Participant-level log for feedback use, revisions, and uptake analysis.</p>
        </div>
        <a className="button-link" href={exportUrl(`/exports/participant/${participantId}`)}>
          <Download size={18} /> CSV
        </a>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task</th><th>Type</th><th>Attempt</th><th>Time</th><th>Condition</th><th>Target</th><th>Transcript</th><th>Score</th><th>Feedback</th><th>Use</th><th>Viewed</th><th>Re-recorded</th><th>Delta</th>
            </tr>
          </thead>
          <tbody>
            {attempts.map((attempt) => (
              <tr key={attempt.id}>
                <td>{attempt.task_id}</td>
                <td>{attempt.task_type}</td>
                <td>{attempt.attempt_number}</td>
                <td>{new Date(attempt.created_at).toLocaleString()}</td>
                <td>{attempt.condition || attempt.group_id}</td>
                <td>{attempt.target_text}</td>
                <td>{attempt.asr_transcript}</td>
                <td>{attempt.score}</td>
                <td>{attempt.feedback_type}</td>
                <td>{attempt.feedback_use_state}</td>
                <td>{attempt.feedback_viewed ? "yes" : "no"}</td>
                <td>{attempt.re_recorded ? "yes" : "no"}</td>
                <td>{attempt.improvement > 0 ? "+" : ""}{attempt.improvement}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
