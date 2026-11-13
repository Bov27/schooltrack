"use client";

import { useMemo, useState } from "react";

import { useSession } from "@/components/Shell";
import { getInstitution, useApi } from "@/lib/client";
import { defaultRange, formatRate } from "@/lib/format";
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

export default function AnalyticsPage() {
  const { isAdmin, membership } = useSession();
  const allowed = isAdmin || (membership?.roles.includes("TEACHER") ?? false);
  const initial = useMemo(() => defaultRange(new Date()), []);
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [campus, setCampus] = useState("");
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const query = `from=${from}&to=${to}${campus ? `&campus_id=${campus}` : ""}`;
  const report = useApi<Report>(allowed ? `analytics/attendance?${query}` : null);
  const campuses = useApi<Campus[]>(allowed ? "campuses" : null);

  if (!allowed) return <div className="panel muted">Only school administrators and teachers can see analytics.</div>;

  async function downloadCsv() {
    setDownloadError(null);
    const headers: HeadersInit = {};
    const institution = getInstitution();
    if (institution) headers["x-institution-id"] = institution;
    const response = await fetch(`/api/backend/analytics/attendance.csv?${query}`, { headers });
    if (!response.ok) {
      setDownloadError(`Export failed (${response.status})`);
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `attendance_${from}_${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const maxPresent = Math.max(1, ...(report.data?.days.map((d) => d.students_present) ?? [1]));

  return (
    <>
      <h2>Analytics</h2>
      <div className="panel">
        <form className="inline" onSubmit={(e) => e.preventDefault()}>
          <label>From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label>To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          <label>
            Campus
            <select value={campus} onChange={(e) => setCampus(e.target.value)}>
              <option value="">All campuses</option>
              {campuses.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <button type="button" className="secondary" onClick={() => void downloadCsv()}>Download CSV</button>
        </form>
        {downloadError && <div className="error" style={{ marginTop: 10 }}>{downloadError}</div>}
        <p className="muted">
          School days are Monday to Friday in the institution&apos;s timezone. A student counts as present on a
          day with an accepted check-in (validated or under review; rejected attempts do not count).
        </p>
      </div>
      {report.error && <div className="error">{report.error}</div>}
      {report.data && (
        <>
          <div className="grid">
            <div className="panel"><div className="muted">School days</div><div className="stat">{report.data.school_days}</div></div>
            <div className="panel"><div className="muted">Overall attendance</div><div className="stat">{formatRate(report.data.overall_rate)}</div></div>
            <div className="panel"><div className="muted">Students</div><div className="stat">{report.data.students.length}</div></div>
          </div>
          <div className="panel">
            <h3>Students present per day</h3>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", height: 140 }}>
              {report.data.days.map((d) => (
                <div key={d.day} style={{ flex: 1, textAlign: "center" }} title={`${d.day}: ${d.students_present}`}>
                  <div style={{ background: "var(--accent)", borderRadius: 4, height: `${(d.students_present / maxPresent) * 100}px` }} />
                  <div className="muted" style={{ fontSize: 11 }}>{d.day.slice(5)}</div>
                  <div style={{ fontSize: 12 }}>{d.students_present}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="panel">
            <h3>Per student</h3>
            <table>
              <thead>
                <tr>
                  <th>Code</th><th>Name</th><th>Days present</th><th>Rate</th><th>Avg. first check-in</th>
                  <th>Flagged</th><th>Rejected</th><th>Manual</th>
                </tr>
              </thead>
              <tbody>
                {report.data.students.map((s) => (
                  <tr key={s.student_id}>
                    <td>{s.student_code}</td>
                    <td>{s.full_name}</td>
                    <td>{s.days_present} / {s.school_days}</td>
                    <td>
                      <span className={`badge ${s.attendance_rate === null ? "neutral" : s.attendance_rate >= 0.9 ? "ok" : s.attendance_rate >= 0.75 ? "warn" : "bad"}`}>
                        {formatRate(s.attendance_rate)}
                      </span>
                    </td>
                    <td>{s.average_first_check_in ?? "–"}</td>
                    <td>{s.flagged_events}</td>
                    <td>{s.rejected_events}</td>
                    <td>{s.manual_events}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
