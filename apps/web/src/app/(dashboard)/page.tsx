"use client";

import Link from "next/link";

import { useSession } from "@/components/Shell";
import { useApi } from "@/lib/client";
import type { AttendanceEvent, Campus, Student } from "@/lib/types";

function Stat({ label, value, href }: { label: string; value: number | undefined; href: string }) {
  return (
    <Link href={href} className="panel" style={{ color: "inherit" }}>
      <div className="muted">{label}</div>
      <div className="stat">{value ?? "–"}</div>
    </Link>
  );
}

export default function Overview() {
  const { me, membership, isAdmin } = useSession();
  const campuses = useApi<Campus[]>(membership ? "campuses" : null);
  const students = useApi<Student[]>(isAdmin ? "students" : null);
  const flagged = useApi<AttendanceEvent[]>(
    isAdmin ? "attendance/events?validation_status=FLAGGED_FOR_REVIEW&limit=200" : null,
  );

  return (
    <>
      <h2>Hello, {me.full_name.split(" ")[0]}</h2>
      {!isAdmin && membership && (
        <div className="panel muted">
          This dashboard is meant for school administrators. Students and staff record attendance from the
          mobile app.
        </div>
      )}
      <div className="grid">
        <Stat label="Campuses" value={campuses.data?.length} href="/campuses" />
        {isAdmin && <Stat label="Students" value={students.data?.length} href="/people" />}
        {isAdmin && <Stat label="Events waiting for review" value={flagged.data?.length} href="/attendance" />}
      </div>
    </>
  );
}
