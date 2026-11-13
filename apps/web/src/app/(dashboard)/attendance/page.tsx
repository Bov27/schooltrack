"use client";

import { Fragment, type FormEvent, useMemo, useState } from "react";

import { CampusMap, type Draft, type MapPoint } from "@/components/CampusMap";
import { Icon } from "@/components/Icon";
import { AdminOnly, Message, PageHead, StatusBadge, useSession } from "@/components/Shell";
import { api, newIdempotencyKey, useApi } from "@/lib/client";
import {
  EVENT_LABELS,
  SOURCE_LABELS,
  formatDateTime,
  initials,
  reasonLabel,
  statusLabel,
  statusTone,
} from "@/lib/format";
import type { AttendanceEvent, Campus, Geofence, Student, ValidationStatus } from "@/lib/types";

const FILTERS: { value: ValidationStatus | ""; label: string }[] = [
  { value: "FLAGGED_FOR_REVIEW", label: "Por revisar" },
  { value: "", label: "Todos" },
  { value: "VALIDATED", label: "Válidos" },
  { value: "REJECTED", label: "Rechazados" },
];

const NO_DRAFT: Draft = { polygon: [], circle: { center: null, radius: 0 } };

/** The event on the campus map: where the phone was, how precise it was, and the geofence. */
function EventMap({ event, who }: { event: AttendanceEvent; who: string }) {
  const geofences = useApi<Geofence[]>(`geofences?campus_id=${event.campus_id}`);
  const location = event.location;
  const probe = useMemo<MapPoint | null>(() => {
    if (!location) return null;
    const tone = statusTone(event.validation_status);
    return {
      id: event.id,
      position: [location.latitude, location.longitude],
      tone: tone === "neutral" ? "warn" : tone,
      label: `${who}: ${statusLabel(event.validation_status)}`,
    };
  }, [event, location, who]);
  if (!location || !probe) return null;

  const accuracy = location.accuracy_m;
  const outside = event.geofence_result === "OUTSIDE";
  return (
    <div className="event-map">
      <CampusMap
        geofences={geofences.data ?? []}
        mode="view"
        draft={NO_DRAFT}
        probe={probe}
        probeAccuracy={accuracy}
        height={340}
      />
      <div className="event-facts">
        <h3>{EVENT_LABELS[event.event_type]} de {who}</h3>
        <dl>
          <dt>Resultado</dt>
          <dd><StatusBadge status={event.validation_status} /></dd>
          <dt>Posición</dt>
          <dd>
            {statusLabel(event.geofence_result)} de la geocerca
            {outside && event.distance_to_geofence_m !== null && `, a ${Math.round(event.distance_to_geofence_m)} m del borde`}
          </dd>
          <dt>Precisión del GPS</dt>
          <dd>{accuracy !== null ? `±${Math.round(accuracy)} m (el círculo de color)` : "Desconocida"}</dd>
          {event.validation_reasons.length > 0 && (
            <>
              <dt>Motivo</dt>
              <dd>{event.validation_reasons.map(reasonLabel).join(". ")}</dd>
            </>
          )}
          <dt>Coordenadas</dt>
          <dd className="num small">
            {location.latitude.toFixed(6)}, {location.longitude.toFixed(6)}
          </dd>
        </dl>
        <p className="muted small">
          Si el círculo de precisión toca el borde de la geocerca, el sistema no puede asegurar de qué lado
          estaba la persona; por eso queda para tu revisión.
        </p>
      </div>
    </div>
  );
}

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

  const [open, setOpen] = useState<string | null>(null);
  const toggle = (id: string) => setOpen((current) => (current === id ? null : id));

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
                <Fragment key={e.id}>
                <tr
                  className={e.location ? "clickable" : undefined}
                  aria-expanded={e.location ? open === e.id : undefined}
                  onClick={(click) => {
                    if (!e.location || (click.target as HTMLElement).closest("button")) return;
                    toggle(e.id);
                  }}
                >
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
                    <td>
                      {e.location ? (
                        <button
                          type="button"
                          className="ghost small"
                          aria-expanded={open === e.id}
                          onClick={() => toggle(e.id)}
                        >
                          <Icon name="pin" size={16} />
                          {open === e.id ? "Ocultar mapa" : "Ver en el mapa"}
                        </button>
                      ) : (
                        <span className="muted small">Sin ubicación</span>
                      )}
                    </td>
                  )}
                  {isAdmin && <td className="actions"><ReviewButtons event={e} onDone={events.reload} /></td>}
                </tr>
                {open === e.id && (
                  <tr className="detail">
                    <td colSpan={isAdmin ? 8 : 6}>
                      <EventMap event={e} who={studentName(e)} />
                    </td>
                  </tr>
                )}
                </Fragment>
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
