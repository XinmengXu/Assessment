import { useState } from "react";
import { Plus, Save } from "lucide-react";
import { api, Task } from "../api/client";

const blank = {
  target_text: "",
  focus_words: "",
  speaking_target: "",
  difficulty: "medium",
  model_audio_path: "",
};

export function TaskManagement({ tasks, onTasks }: { tasks: Task[]; onTasks: (tasks: Task[]) => void }) {
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState<number | null>(null);

  function edit(task: Task) {
    setEditingId(task.id);
    setForm({
      target_text: task.target_text,
      focus_words: task.focus_words.join(", "),
      speaking_target: task.speaking_target,
      difficulty: task.difficulty,
      model_audio_path: task.model_audio_path,
    });
  }

  async function save() {
    const payload = {
      ...form,
      focus_words: form.focus_words.split(",").map((word) => word.trim()).filter(Boolean),
    };
    const path = editingId ? `/tasks/${editingId}` : "/tasks";
    const method = editingId ? "PUT" : "POST";
    await api<Task>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const updated = await api<Task[]>("/tasks");
    onTasks(updated);
    setForm(blank);
    setEditingId(null);
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="section-head"><h2>{editingId ? "Edit Task" : "Add Task"}</h2></div>
        <label>Target sentence<textarea value={form.target_text} onChange={(event) => setForm({ ...form, target_text: event.target.value })} /></label>
        <label>Focus words<input value={form.focus_words} onChange={(event) => setForm({ ...form, focus_words: event.target.value })} placeholder="comma separated" /></label>
        <label>Speaking target<input value={form.speaking_target} onChange={(event) => setForm({ ...form, speaking_target: event.target.value })} /></label>
        <label>Difficulty<select value={form.difficulty} onChange={(event) => setForm({ ...form, difficulty: event.target.value })}><option>easy</option><option>medium</option><option>hard</option></select></label>
        <label>Model audio path<input value={form.model_audio_path} onChange={(event) => setForm({ ...form, model_audio_path: event.target.value })} /></label>
        <button className="primary submit" onClick={save}>{editingId ? <Save size={18} /> : <Plus size={18} />} Save task</button>
      </div>
      <div className="panel">
        <h2>Existing Tasks</h2>
        <div className="task-list">
          {tasks.map((task) => (
            <button key={task.id} onClick={() => edit(task)}>
              <strong>Task {task.id}</strong>
              <span>{task.target_text}</span>
              <small>{task.speaking_target} · {task.difficulty}</small>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
