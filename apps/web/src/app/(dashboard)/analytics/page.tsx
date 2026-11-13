"use client";

import { useMemo, useState } from "react";

import { Icon } from "@/components/Icon";
import { Message, PageHead, useSession } from "@/components/Shell";
import { getInstitution, useApi } from "@/lib/client";
import { defaultRange, formatRate, initials } from "@/lib/format";
import type { Campus } from "@/lib/types";

interface StudentRow {
  student_id: string;
  student_code: string;
  full_name: string;
  days_present: number;
  school_days: number;
  attendance_rate: number | null;
  average_first_check_in: string | null;
  flagged_events: number;
  rejected_events: number;
  manual_events: number;
}

interface Report {
  start: string;
  end: string;
  timezone: string;
  school_days: number;
  overall_rate: number | null;
  students: StudentRow[];
  days: { day: string; students_present: number }[];
}

function rateColor(rate: number | null): string {
  if (rate === null) return "#cdd2cb";
  if (rate >= 0.9) return "var(--pizarra)";
  if (rate >= 0.75) return "var(--pupitre)";
  return "var(--lacre)";
}

function dayLabel(iso: string): string {
  const date = new Date(`${iso}T12:00:00`);
  return new Intl.DateTimeFormat("es-CO", { weekday: "short", day: "numeric" }).format(date);
}

export default function AnalyticsPage() {
  const { isAdmin, isTeacher } = useSession();
  const allowed = isAdmin || isTeacher;
  const initial = useMemo(() => defaultRange(new Date()), []);
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [campus, setCampus] = useState("");
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const query = `from=${from}&to=${to}${campus ? `&campus_id=${campus}` : ""}`;
  const report = useApi<Report>(allowed ? `analytics/attendance?${query}` : null);
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

  const data = report.data;
  const maxPresent = Math.max(1, ...(data?.days.map((d) => d.students_present) ?? [1]));
  const sorted = [...(data?.students ?? [])].sort(
    (a, b) => (a.attendance_rate ?? 2) - (b.attendance_rate ?? 2) || a.full_name.localeCompare(b.full_name),
  );

  return (
    <>
      <PageHead
        title="Analíticas"
        actions={
          <button type="button" className="secondary" onClick={() => void downloadCsv()}>
            <Icon name="download" size={18} />
            Descargar CSV
          </button>
        }
      >
        Días hábiles de lunes a viernes en la zona horaria de la institución. Cuenta como presente quien tiene
        una entrada aceptada ese día; los intentos rechazados no cuentan.
      </PageHead>

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
      </form>
      {downloadError && <Message tone="error">{downloadError}</Message>}
      {report.error && <Message tone="error">{report.error}</Message>}

      {data && (
        <>
          <div className="stat-line">
            <div><b className="num">{formatRate(data.overall_rate)}</b><span>asistencia general</span></div>
            <div><b className="num">{data.school_days}</b><span>días hábiles</span></div>
            <div><b className="num">{data.students.length}</b><span>estudiantes</span></div>
          </div>

          <section className="panel">
            <div className="panel-head"><h2>Estudiantes presentes por día</h2></div>
            {data.days.length === 0 ? (
              <p className="empty">No hay días hábiles en este rango.</p>
            ) : (
              <div className="bars" role="list">
                {data.days.map((d, i) => (
                  <div key={d.day} className="bar" role="listitem" aria-label={`${dayLabel(d.day)}: ${d.students_present}`}>
                    <span className="bar-value num">{d.students_present}</span>
                    <span
                      className="bar-fill"
                      style={{ height: `${(d.students_present / maxPresent) * 130}px`, animationDelay: `${i * 40}ms` }}
                    />
                    <span className="bar-label">{dayLabel(d.day)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Por estudiante</h2>
              <span className="muted small">De menor a mayor asistencia</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Estudiante</th><th>Días presente</th><th>Asistencia</th><th>Llegada promedio</th>
                    <th>Por revisar</th><th>Rechazados</th><th>Manuales</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((s) => (
                    <tr key={s.student_id}>
                      <td>
                        <span className="person">
                          <span className="avatar">{initials(s.full_name)}</span>
                          <span>
                            <strong>{s.full_name}</strong>
                            <div className="muted small">{s.student_code}</div>
                          </span>
                        </span>
                      </td>
                      <td className="num">{s.days_present} de {s.school_days}</td>
                      <td>
                        <span className="rate">
                          <span className="rate-track">
                            <span style={{ width: `${(s.attendance_rate ?? 0) * 100}%`, background: rateColor(s.attendance_rate) }} />
                          </span>
                          <strong className="num">{formatRate(s.attendance_rate)}</strong>
                        </span>
                      </td>
                      <td className="num">{s.average_first_check_in ?? "–"}</td>
                      <td className="num">{s.flagged_events || "–"}</td>
                      <td className="num">{s.rejected_events || "–"}</td>
                      <td className="num">{s.manual_events || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sorted.length === 0 && <p className="empty">No hay estudiantes registrados.</p>}
          </section>
        </>
      )}
    </>
  );
}
