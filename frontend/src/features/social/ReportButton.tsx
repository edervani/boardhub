import { useId, useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { ReportReason } from "../../services/types";

export const REASON_LABEL: Record<ReportReason, string> = {
  offensive_name: "Apelido ofensivo",
  offensive_bio: "Bio ofensiva",
  cheating: "Suspeita de trapaça",
  harassment: "Assédio ou comportamento abusivo",
  other: "Outro motivo",
};

interface Props {
  targetType: "user" | "match";
  /** Apelido público (usuário) ou id da partida. */
  targetId: string;
  label?: string;
}

/** Denúncia (RF-031). O denunciado não vê quem denunciou; o texto livre é só texto. */
export function ReportButton({ targetType, targetId, label = "Denunciar" }: Props) {
  const uid = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason>(targetType === "match" ? "cheating" : "harassment");
  const [note, setNote] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const reasons = (Object.keys(REASON_LABEL) as ReportReason[]).filter(
    (r) => targetType === "user" || (r !== "offensive_name" && r !== "offensive_bio"),
  );

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    try {
      await api("POST", "/reports", {
        target_type: targetType, target_id: targetId, reason, note: note.trim() || null,
      });
      setDone(true); setOpen(false); setNote("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (done) return <p role="status">Denúncia enviada. A moderação vai analisar, sem revelar quem denunciou.</p>;
  if (!open) {
    return (
      <>
        <button type="button" className="secondary" onClick={() => setOpen(true)}>{label}</button>
        {error && <p role="alert">{error}</p>}
      </>
    );
  }
  return (
    <form onSubmit={(e) => void submit(e)} aria-labelledby={`${uid}-t`} className="card">
      <h4 id={`${uid}-t`}>Denunciar</h4>
      <label htmlFor={`${uid}-r`}>Motivo</label>
      <select id={`${uid}-r`} value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
        {reasons.map((r) => <option key={r} value={r}>{REASON_LABEL[r]}</option>)}
      </select>
      <label htmlFor={`${uid}-n`}>Detalhes (opcional, até 500 caracteres)</label>
      <textarea id={`${uid}-n`} maxLength={500} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      <p>Não envie dados pessoais. Quem foi denunciado não sabe quem denunciou.</p>
      <button type="submit">Enviar denúncia</button>{" "}
      <button type="button" className="secondary" onClick={() => setOpen(false)}>Cancelar</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
