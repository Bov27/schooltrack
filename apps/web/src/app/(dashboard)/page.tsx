"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Message, PageHead, useSession } from "@/components/Shell";
import { useApi } from "@/lib/client";
import { EVENT_LABELS, STATE_LABELS, formatTime, initials, reasonLabel } from "@/lib/format";
import type { AttendanceEvent, AttendanceState, Campus, RosterEntry, Student } from "@/lib/types";

type Filter = AttendanceState | "ALL";
const FILTERS: { value: Filter; label: string }[] = [
  { value: "ALL", label: "Todos" },
  { value: "PRESENT", label: "En el colegio" },
  { value: "TEMPORARY_EXIT", label: "Salida temporal" },
  { value: "OUTSIDE", label: "Fuera" },
];
const REFRESH_MS = 30_000;

function isToday(iso: string | null): boolean {
  if (!iso) return false;
  const day = (d: Date) => d.toLocaleDateString("es-CO", { timeZone: "America/Bogota" });
  return day(new Date(iso)) === day(new Date());
}

function seatMeta(entry: RosterEntry): string {
  if (!entry.last_event_type || !entry.last_event_at || !isToday(entry.last_event_at)) {
    return "Sin registros hoy";
  }
  return `${EVENT_LABELS[entry.last_event_type]} a las ${formatTime(entry.last_event_at)}`;
}

function RollCall({ campuses, flagged }: { campuses: number | undefined; flagged: AttendanceEvent[] | undefined }) {
  const { isAdmin } = useSession();
  const roster = useApi<RosterEntry[]>("attendance/roster");
  const students = useApi<Student[]>(isAdmin ? "students" : null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const { reload } = roster;

  useEffect(() => {
    const timer = window.setInterval(reload, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [reload]);

  const counts = useMemo(() => {
    const all = roster.data ?? [];
    return {
      ALL: all.length,
      PRESENT: all.filter((r) => r.state === "PRESENT").length,
      TEMPORARY_EXIT: all.filter((r) => r.state === "TEMPORARY_EXIT").length,
      OUTSIDE: all.filter((r) => r.state === "OUTSIDE").length,
    };
  }, [roster.data]);

  const names = useMemo(() => new Map(students.data?.map((s) => [s.id, s.full_name])), [students.data]);
  const visible = (roster.data ?? []).filter((r) => filter === "ALL" || r.state === filter);
  const total = Math.max(counts.ALL, 1);

  return (
    <div className="split">
      <section className="panel" aria-labelledby="roll-title">
        <h2 id="roll-title" className="headline">
          <span className="big num">{roster.data ? counts.PRESENT : "–"}</span>
          {roster.data && (
            <>
              <span className="of">de {counts.ALL} estudiantes</span> están en el colegio ahora
            </>
          )}
        </h2>
        <div className="meter" aria-hidden="true">
          <span className="present" style={{ flexGrow: counts.PRESENT / total }} />
          <span className="temporary" style={{ flexGrow: counts.TEMPORARY_EXIT / total }} />
        </div>
        <div className="legend">
          <span><i style={{ background: "var(--pizarra)" }} />En el colegio</span>
          <span><i style={{ background: "var(--pupitre)" }} />Salida temporal, {counts.TEMPORARY_EXIT}</span>
          <span><i style={{ background: "#cdd2cb" }} />Fuera, {counts.OUTSIDE}</span>
        </div>

        <div style={{ marginTop: 26 }} className="segmented" role="group" aria-label="Filtrar estudiantes">
          {FILTERS.map((f) => (
            <button key={f.value} aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
              {f.label}
              <span className="count num">{counts[f.value]}</span>
            </button>
          ))}
        </div>

        {roster.error && <Message tone="error">{roster.error}</Message>}
        <ul className="roll" style={{ listStyle: "none", padding: 0 }}>
          {visible.map((entry, index) => (
            <li
              key={entry.student_id}
              className="seat"
              data-state={entry.state}
              style={{ animationDelay: `${Math.min(index, 24) * 18}ms` }}
              title={`${entry.full_name}: ${STATE_LABELS[entry.state]}`}
            >
              <span className="avatar">{initials(entry.full_name)}</span>
              <span>
                <span className="seat-name">{entry.full_name}</span>
                <br />
                <span className="seat-meta">{seatMeta(entry)}</span>
              </span>
            </li>
          ))}
        </ul>
        {roster.data && visible.length === 0 && (
          <p className="empty">
            {counts.ALL === 0 ? (
              <>Aún no hay estudiantes. <Link href="/people">Registra el primero</Link>.</>
            ) : (
              "Nadie en este grupo por ahora."
            )}
          </p>
        )}
        <p className="muted small" style={{ marginTop: 16 }}>Se actualiza cada 30 segundos.</p>
      </section>

      <aside>
        {isAdmin && (
          <section className="panel" aria-labelledby="review-title">
            <div className="panel-head">
              <h2 id="review-title">Por revisar</h2>
              {flagged && flagged.length > 0 && <Link href="/attendance">Ver todos</Link>}
            </div>
            {flagged?.length === 0 && <p className="muted">No hay registros pendientes de revisión.</p>}
            {flagged?.slice(0, 5).map((event) => (
              <div key={event.id} className="review-item">
                <span className="review-dot" />
                <div>
                  <strong>{event.student_id ? (names.get(event.student_id) ?? "Estudiante") : "Funcionario"}</strong>
                  <div className="muted small">
                    {EVENT_LABELS[event.event_type]} a las {formatTime(event.occurred_at)}
                  </div>
                  <div className="small">{event.validation_reasons.map(reasonLabel).join(". ")}</div>
                </div>
              </div>
            ))}
          </section>
        )}
        <section className="facts">
          <div className="fact">
            <Link href="/campuses">
              <b className="num">{campuses ?? "–"}</b>
              {campuses === 1 ? "sede" : "sedes"}
            </Link>
          </div>
          <div className="fact">
            <Link href="/analytics">
              <b className="num">{counts.ALL}</b>
              estudiantes
            </Link>
          </div>
        </section>
      </aside>
    </div>
  );
}

export default function Overview() {
  const { me, membership, isAdmin, isTeacher } = useSession();
  const campuses = useApi<Campus[]>(membership ? "campuses" : null);
  const flagged = useApi<AttendanceEvent[]>(
    isAdmin ? "attendance/events?validation_status=FLAGGED_FOR_REVIEW&limit=200" : null,
  );
  const today = new Intl.DateTimeFormat("es-CO", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "America/Bogota",
  }).format(new Date());

  return (
    <>
      <PageHead title={`Hola, ${me.full_name.split(" ")[0]}`}>
        {membership ? `${membership.institution_name}, ${today}.` : today}
      </PageHead>
      {isAdmin || isTeacher ? (
        <RollCall campuses={campuses.data?.length} flagged={flagged.data} />
      ) : (
        membership && (
          <Message tone="notice">
            Este panel es para la administración y los docentes. Estudiantes, funcionarios y acudientes usan
            la app móvil.
          </Message>
        )
      )}
    </>
  );
}
