"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { Message, PageHead, useSession } from "@/components/Shell";
import { getInstitution, useApi } from "@/lib/client";
import { defaultRange, formatRate, initials } from "@/lib/format";
import type { Campus } from "@/lib/types";

interface Counts {
  days_present: number;
  school_days: number;
  attendance_rate: number | null;
  average_first_check_in: string | null;
  flagged_events: number;
  rejected_events: number;
  manual_events: number;
}
interface StudentRow extends Counts {
  student_id: string;
  student_code: string;
  full_name: string;
}
interface StaffRow extends Counts {
  staff_id: string;
  employee_code: string;
  staff_type: "TEACHER" | "ADMINISTRATIVE" | "SUPPORT";
  full_name: string;
  average_last_check_out: string | null;
}
interface StudentReport {
  school_days: number;
  overall_rate: number | null;
  students: StudentRow[];
  days: { day: string; students_present: number }[];
}
interface StaffReport {
  school_days: number;
  overall_rate: number | null;
  staff: StaffRow[];
  days: { day: string; present: number }[];
}
interface PersonDay {
  day: string;
  present: boolean;
  first_check_in: string | null;
  last_check_out: string | null;
  flagged_events: number;
  rejected_events: number;
  events: number;
}
interface PersonReport {
  full_name: string;
  code: string;
  school_days: number;
  days_present: number;
  attendance_rate: number | null;
  days: PersonDay[];
}

type Group = "students" | "staff";
interface Selected {
  kind: "student" | "staff";
  id: string;
}

const STAFF_TYPES: Record<StaffRow["staff_type"], string> = {
  TEACHER: "Docente",
  ADMINISTRATIVE: "Administrativo",
  SUPPORT: "Apoyo",
};
const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie"];

function rateColor(rate: number | null): string {
  if (rate === null) return "#cdd2cb";
  if (rate >= 0.9) return "var(--pizarra)";
  if (rate >= 0.75) return "var(--pupitre)";
  return "var(--lacre)";
}

function localDate(iso: string): Date {
  return new Date(`${iso}T12:00:00`);
}

function dayLabel(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", { weekday: "short", day: "numeric" }).format(localDate(iso));
}

function sortByRate<T extends Counts & { full_name: string }>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) => (a.attendance_rate ?? 2) - (b.attendance_rate ?? 2) || a.full_name.localeCompare(b.full_name),
  );
}

/** School days laid out as weeks (Monday to Friday), so gaps are easy to spot. */
function weeks(days: PersonDay[]): (PersonDay | null)[][] {
  const rows: (PersonDay | null)[][] = [];
  let current: (PersonDay | null)[] | null = null;
  for (const day of days) {
    const weekday = (localDate(day.day).getDay() + 6) % 7; // 0 = Monday
    if (current === null || weekday === 0) {
      current = [null, null, null, null, null];
      rows.push(current);
    }
    current[weekday] = day;
  }
  return rows;
}

function dayState(day: PersonDay, today: string): { className: string; text: string } {
  if (day.day > today) return { className: "future", text: "Próximo" };
  if (day.present) return { className: day.flagged_events ? "flagged" : "present", text: "Asistió" };
  if (day.rejected_events) return { className: "rejected", text: "Intento rechazado" };
  return { className: "absent", text: "No asistió" };
}

function PersonDetail({ selected, query, onClose }: { selected: Selected; query: string; onClose: () => void }) {
  const param = selected.kind === "student" ? "student_id" : "staff_id";
  const report = useApi<PersonReport>(`analytics/person?${query}&${param}=${selected.id}`);
  const ref = useRef<HTMLElement>(null);
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });

  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selected.id]);

  const data = report.data;
  return (
    <section ref={ref} className="panel person-detail" aria-live="polite">
      <div className="panel-head">
        <div className="person">
          <span className="avatar">{initials(data?.full_name ?? "")}</span>
          <div>
            <h2>{data?.full_name ?? "Cargando…"}</h2>
            {data && <div className="muted small">{data.code}</div>}
          </div>
        </div>
        <button type="button" className="ghost" onClick={onClose} aria-label="Cerrar detalle">
          <Icon name="close" />
        </button>
      </div>
      {report.error && <Message tone="error">{report.error}</Message>}
      {data && (
        <>
          <div className="stat-line">
            <div><b className="num">{formatRate(data.attendance_rate)}</b><span>asistencia</span></div>
            <div><b className="num">{data.days_present}</b><span>días que asistió</span></div>
            <div>
              <b className="num">{data.days.filter((d) => !d.present && d.day <= today).length}</b>
              <span>días que no asistió</span>
            </div>
          </div>
          <div className="calendar" role="table" aria-label="Asistencia por día">
            <div className="calendar-row calendar-head" role="row">
              {WEEKDAYS.map((w) => <span key={w} role="columnheader">{w}</span>)}
            </div>
            {weeks(data.days).map((week, i) => (
              <div key={i} className="calendar-row" role="row">
                {week.map((day, j) => {
                  if (!day) return <span key={j} className="calendar-day empty" role="cell" />;
                  const state = dayState(day, today);
                  return (
                    <span
                      key={day.day}
                      role="cell"
                      className={`calendar-day ${state.className}`}
                      title={`${dayLabel(day.day)}: ${state.text}`}
                    >
                      <span className="calendar-date">{localDate(day.day).getDate()}</span>
                      <span className="calendar-state">{state.text}</span>
                      {day.first_check_in && (
                        <span className="calendar-times num">
                          {day.first_check_in}
                          {day.last_check_out ? ` a ${day.last_check_out}` : ""}
                        </span>
                      )}
                      {day.flagged_events > 0 && <span className="calendar-note">En revisión</span>}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="legend" style={{ marginTop: 14 }}>
            <span><i style={{ background: "var(--pizarra)" }} />Asistió</span>
            <span><i style={{ background: "var(--pupitre)" }} />Asistió, en revisión</span>
            <span><i style={{ background: "#f3c9c4" }} />No asistió</span>
            <span><i style={{ background: "var(--lacre)" }} />Intento rechazado</span>
          </div>
        </>
      )}
    </section>
  );
}

function Bars({ days }: { days: { day: string; value: number }[] }) {
  const max = Math.max(1, ...days.map((d) => d.value));
  if (days.length === 0) return <p className="empty">No hay días hábiles en este rango.</p>;
  return (
    <div className="bars" role="list">
      {days.map((d, i) => (
        <div key={d.day} className="bar" role="listitem" aria-label={`${dayLabel(d.day)}: ${d.value}`}>
          <span className="bar-value num">{d.value}</span>
          <span
            className="bar-fill"
            style={{ height: `${(d.value / max) * 130}px`, animationDelay: `${i * 40}ms` }}
          />
          <span className="bar-label">{dayLabel(d.day)}</span>
        </div>
      ))}
    </div>
  );
}

function RateCell({ rate }: { rate: number | null }) {
  return (
    <span className="rate">
      <span className="rate-track">
        <span style={{ width: `${(rate ?? 0) * 100}%`, background: rateColor(rate) }} />
      </span>
      <strong className="num">{formatRate(rate)}</strong>
    </span>
  );
}

export default function AnalyticsPage() {
  const { isAdmin, isTeacher } = useSession();
  const allowed = isAdmin || isTeacher;
  const initial = useMemo(() => defaultRange(new Date()), []);
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [campus, setCampus] = useState("");
  const [group, setGroup] = useState<Group>("students");
  const [selected, setSelected] = useState<Selected | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const query = `from=${from}&to=${to}${campus ? `&campus_id=${campus}` : ""}`;
  const students = useApi<StudentReport>(allowed && group === "students" ? `analytics/attendance?${query}` : null);
  const staff = useApi<StaffReport>(isAdmin && group === "staff" ? `analytics/staff?${query}` : null);
  const campuses = useApi<Campus[]>(allowed ? "campuses" : null);

  if (!allowed) return <Message tone="notice">Solo la administración y los docentes ven las analíticas.</Message>;

  async function downloadCsv() {
    setDownloadError(null);
    const headers: HeadersInit = {};
    const institution = getInstitution();
    if (institution) headers["x-institution-id"] = institution;
    const response = await fetch(`/api/backend/analytics/attendance.csv?${query}`, { headers });
    if (!response.ok) {
      setDownloadError(`No se pudo descargar el archivo (error ${response.status}).`);
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `asistencia_${from}_${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const report = group === "students" ? students : staff;
  const rows =
    group === "students"
      ? sortByRate(students.data?.students ?? []).map((s) => ({ ...s, id: s.student_id, code: s.student_code, sub: s.student_code }))
      : sortByRate(staff.data?.staff ?? []).map((s) => ({
          ...s,
          id: s.staff_id,
          code: s.employee_code,
          sub: `${STAFF_TYPES[s.staff_type]}, ${s.employee_code}`,
        }));
  const people = [...rows].sort((a, b) => a.full_name.localeCompare(b.full_name));
  const summary = group === "students" ? students.data : staff.data;
  const days =
    group === "students"
      ? (students.data?.days ?? []).map((d) => ({ day: d.day, value: d.students_present }))
      : (staff.data?.days ?? []).map((d) => ({ day: d.day, value: d.present }));
  const kind = group === "students" ? "student" : "staff";

  return (
    <>
      <PageHead
        title="Analíticas"
        actions={
          group === "students" ? (
            <button type="button" className="secondary" onClick={() => void downloadCsv()}>
              <Icon name="download" size={18} />
              Descargar CSV
            </button>
          ) : undefined
        }
      >
        Días hábiles de lunes a viernes en la zona horaria de la institución. Cuenta como presente quien tiene
        una entrada aceptada ese día; los intentos rechazados no cuentan.
      </PageHead>

      {isAdmin && (
        <div className="segmented" role="group" aria-label="Grupo" style={{ marginBottom: 20 }}>
          <button type="button" aria-pressed={group === "students"} onClick={() => { setGroup("students"); setSelected(null); }}>
            Estudiantes
          </button>
          <button type="button" aria-pressed={group === "staff"} onClick={() => { setGroup("staff"); setSelected(null); }}>
            Docentes y funcionarios
          </button>
        </div>
      )}

      <form className="inline" onSubmit={(e) => e.preventDefault()} style={{ marginBottom: 24 }}>
        <label>Desde<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>Hasta<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label>
          Sede
          <select value={campus} onChange={(e) => setCampus(e.target.value)}>
            <option value="">Todas las sedes</option>
            {campuses.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label style={{ minWidth: 240 }}>
          {group === "students" ? "Ver un estudiante" : "Ver una persona"}
          <select
            value={selected?.id ?? ""}
            onChange={(e) => setSelected(e.target.value ? { kind, id: e.target.value } : null)}
          >
            <option value="">Elegir…</option>
            {people.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.code})</option>)}
          </select>
        </label>
      </form>
      {downloadError && <Message tone="error">{downloadError}</Message>}
      {report.error && <Message tone="error">{report.error}</Message>}

      {selected && <PersonDetail selected={selected} query={query} onClose={() => setSelected(null)} />}

      {summary && (
        <>
          <div className="stat-line">
            <div><b className="num">{formatRate(summary.overall_rate)}</b><span>asistencia general</span></div>
            <div><b className="num">{summary.school_days}</b><span>días hábiles</span></div>
            <div>
              <b className="num">{rows.length}</b>
              <span>{group === "students" ? "estudiantes" : "docentes y funcionarios"}</span>
            </div>
          </div>

          <section className="panel">
            <div className="panel-head">
              <h2>{group === "students" ? "Estudiantes presentes por día" : "Personal presente por día"}</h2>
            </div>
            <Bars days={days} />
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>{group === "students" ? "Por estudiante" : "Por persona"}</h2>
              <span className="muted small">De menor a mayor asistencia. Toca una fila para ver sus días.</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{group === "students" ? "Estudiante" : "Persona"}</th>
                    <th>Días presente</th>
                    <th>Asistencia</th>
                    <th>Llegada promedio</th>
                    {group === "staff" && <th>Salida promedio</th>}
                    <th>Por revisar</th>
                    <th>Rechazados</th>
                    <th>Manuales</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => (
                    <tr
                      key={s.id}
                      className="clickable"
                      aria-selected={selected?.id === s.id}
                      tabIndex={0}
                      onClick={() => setSelected({ kind, id: s.id })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelected({ kind, id: s.id });
                        }
                      }}
                    >
                      <td>
                        <span className="person">
                          <span className="avatar">{initials(s.full_name)}</span>
                          <span>
                            <strong>{s.full_name}</strong>
                            <div className="muted small">{s.sub}</div>
                          </span>
                        </span>
                      </td>
                      <td className="num">{s.days_present} de {s.school_days}</td>
                      <td><RateCell rate={s.attendance_rate} /></td>
                      <td className="num">{s.average_first_check_in ?? "–"}</td>
                      {group === "staff" && (
                        <td className="num">{"average_last_check_out" in s ? (s.average_last_check_out ?? "–") : "–"}</td>
                      )}
                      <td className="num">{s.flagged_events || "–"}</td>
                      <td className="num">{s.rejected_events || "–"}</td>
                      <td className="num">{s.manual_events || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length === 0 && (
              <p className="empty">
                {group === "students" ? "No hay estudiantes registrados." : "No hay docentes ni funcionarios registrados."}
              </p>
            )}
          </section>
        </>
      )}
    </>
  );
}
