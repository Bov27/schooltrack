"use client";

import { type FormEvent, useMemo, useState } from "react";

import { Icon } from "@/components/Icon";
import { AdminOnly, Message, PageHead, StatusBadge, useSession } from "@/components/Shell";
import { api, newIdempotencyKey, useApi } from "@/lib/client";
import { EVENT_LABELS, SOURCE_LABELS, formatDateTime, initials, reasonLabel } from "@/lib/format";
import type { AttendanceEvent, Campus, Student, ValidationStatus } from "@/lib/types";

const FILTERS: { value: ValidationStatus | ""; label: string }[] = [
  { value: "FLAGGED_FOR_REVIEW", label: "Por revisar" },
  { value: "", label: "Todos" },
  { value: "VALIDATED", label: "Válidos" },
  { value: "REJECTED", label: "Rechazados" },
];

function ReviewButtons({ event, onDone }: { event: AttendanceEvent; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  if (event.validation_status !== "FLAGGED_FOR_REVIEW" && event.validation_status !== "PENDING") return null;

  async function decide(decision: "VALIDATED" | "REJECTED") {
    const note = window.prompt(
      decision === "VALIDATED" ? "¿Por qué este registro es válido?" : "¿Por qué se rechaza este registro?",
    );
    if (!note || note.trim().length < 3) return;
    try {
      await api(`attendance/events/${event.id}/review`, {
        method: "POST",
        body: JSON.stringify({ decision, note: note.trim() }),
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <button className="ok small" onClick={() => void decide("VALIDATED")}>
        <Icon name="check" size={16} />
        Aprobar
      </button>
      <button className="danger small" onClick={() => void decide("REJECTED")}>
        Rechazar
      </button>
      {error && <div className="error small">{error}</div>}
    </>
  );
}

function ManualEventForm({ students, campuses, onDone }: {
  students: Student[];
  campuses: Campus[];
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    setError(null);
    setOk(null);
    try {
      await api("attendance/manual-events", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: newIdempotencyKey(),
          event_type: form.get("event_type"),
          campus_id: form.get("campus_id"),
          student_id: form.get("student_id"),
          reason: form.get("reason"),
        }),
      });
      target.reset();
      setOk("Registro manual guardado. Queda en el historial de auditoría.");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <form className="inline" onSubmit={submit}>
      {error && <div style={{ width: "100%" }}><Message tone="error">{error}</Message></div>}
      {ok && <div style={{ width: "100%" }}><Message tone="success">{ok}</Message></div>}
      <label>
        Estudiante
        <select name="student_id" required>
          {students.map((s) => <option key={s.id} value={s.id}>{s.full_name} ({s.student_code})</option>)}
        </select>
      </label>
      <label>
        Sede
        <select name="campus_id" required>
          {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label>
        Acción
        <select name="event_type">
          {Object.entries(EVENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label style={{ flex: "1 1 220px" }}>
        Motivo
        <input name="reason" minLength={3} required placeholder="No trae celular, grado primero" />
      </label>
      <button type="submit">Guardar registro</button>
    </form>
  );
}

export default function AttendancePage() {
  const { isAdmin } = useSession();
  const [filter, setFilter] = useState<ValidationStatus | "">(isAdmin ? "FLAGGED_FOR_REVIEW" : "");
  const events = useApi<AttendanceEvent[]>(
    `attendance/events?limit=200${filter ? `&validation_status=${filter}` : ""}`,
  );
  const students = useApi<Student[]>(isAdmin ? "students" : null);
  const campuses = useApi<Campus[]>("campuses");

  const studentName = useMemo(() => {
    const names = new Map(students.data?.map((s) => [s.id, s.full_name]));
    return (e: AttendanceEvent) => (e.student_id ? (names.get(e.student_id) ?? "Estudiante") : "Funcionario");
  }, [students.data]);
  const campusName = useMemo(() => {
    const names = new Map(campuses.data?.map((c) => [c.id, c.name]));
    return (id: string) => names.get(id) ?? "Sede";
  }, [campuses.data]);

  return (
    <>
      <PageHead title="Registros">
        Cada entrada y salida, con su validación. Los registros en el borde de la geocerca esperan tu revisión.
      </PageHead>
      <AdminOnly>
        <details className="panel">
          <summary>
            Registrar asistencia manual
            <Icon name="plus" />
          </summary>
          <p className="muted" style={{ marginBottom: 14 }}>
            Para quien no puede usar la app. El motivo queda guardado en la auditoría.
          </p>
          {students.data && campuses.data && (
            <ManualEventForm students={students.data} campuses={campuses.data} onDone={events.reload} />
          )}
        </details>
      </AdminOnly>
      <section className="panel">
        <div className="panel-head">
          <div className="segmented" role="group" aria-label="Filtrar por estado">
            {FILTERS.map((f) => (
              <button key={f.value} aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
                {f.label}
              </button>
            ))}
          </div>
          {events.data && <span className="muted num">{events.data.length} registros</span>}
        </div>
        {events.error && <Message tone="error">{events.error}</Message>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Persona</th><th>Acción</th><th>Cuándo</th><th>Sede</th><th>Estado</th><th>Motivo</th>
                {isAdmin && <th>Ubicación</th>}
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {events.data?.map((e) => (
                <tr key={e.id}>
                  <td>
                    <span className="person">
                      <span className="avatar">{initials(studentName(e))}</span>
                      <strong>{studentName(e)}</strong>
                    </span>
                  </td>
                  <td>
                    {EVENT_LABELS[e.event_type]}
                    <div className="muted small">{SOURCE_LABELS[e.source]}</div>
                  </td>
                  <td className="num">{formatDateTime(e.occurred_at)}</td>
                  <td>{campusName(e.campus_id)}</td>
                  <td><StatusBadge status={e.validation_status} /></td>
                  <td className="muted small">{e.validation_reasons.map(reasonLabel).join(". ") || "–"}</td>
                  {isAdmin && (
                    <td className="muted small num">
                      {e.location
                        ? `${e.location.latitude.toFixed(5)}, ${e.location.longitude.toFixed(5)} (±${Math.round(e.location.accuracy_m ?? 0)} m)`
                        : "–"}
                    </td>
                  )}
                  {isAdmin && <td className="actions"><ReviewButtons event={e} onDone={events.reload} /></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {events.data?.length === 0 && (
          <p className="empty">
            {filter === "FLAGGED_FOR_REVIEW" ? "No hay registros por revisar." : "No hay registros con este filtro."}
          </p>
        )}
      </section>
    </>
  );
}
