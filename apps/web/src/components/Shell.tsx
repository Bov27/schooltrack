"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, createContext, useContext, useEffect, useState } from "react";

import { getInstitution, setInstitution, useApi } from "@/lib/client";
import { statusTone } from "@/lib/format";
import type { Me, Membership } from "@/lib/types";

interface Session {
  me: Me;
  membership: Membership | null;
  isAdmin: boolean;
}

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error("useSession must be used inside <Shell>");
  return session;
}

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/attendance", label: "Attendance" },
  { href: "/campuses", label: "Campuses & geofences" },
  { href: "/people", label: "Students & staff" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: me, error } = useApi<Me>("users/me");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    const stored = getInstitution();
    const valid = me.memberships.find((m) => m.institution_id === stored);
    const choice = valid?.institution_id ?? me.memberships[0]?.institution_id ?? null;
    if (choice) setInstitution(choice);
    setSelected(choice);
  }, [me]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  if (error) return <main><div className="error">{error}</div></main>;
  if (!me) return <main className="muted">Loading…</main>;

  const membership = me.memberships.find((m) => m.institution_id === selected) ?? null;
  const session: Session = {
    me,
    membership,
    isAdmin: membership?.roles.includes("SCHOOL_ADMIN") ?? false,
  };

  return (
    <SessionContext.Provider value={session}>
      <div className="layout">
        <nav className="sidebar">
          <h1>SchoolTrack</h1>
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className={pathname === link.href ? "active" : ""}>
              {link.label}
            </Link>
          ))}
          {me.is_platform_admin && (
            <Link href="/institutions" className={pathname === "/institutions" ? "active" : ""}>
              Institutions (platform)
            </Link>
          )}
          <div className="spacer" />
          {me.memberships.length > 1 && (
            <select
              aria-label="Institution"
              value={selected ?? ""}
              onChange={(e) => {
                setInstitution(e.target.value);
                window.location.reload();
              }}
            >
              {me.memberships.map((m) => (
                <option key={m.institution_id} value={m.institution_id}>
                  {m.institution_name}
                </option>
              ))}
            </select>
          )}
          <div className="muted" style={{ color: "#94a3b8" }}>
            {me.full_name}
            <br />
            {membership ? `${membership.institution_name} · ${membership.roles.join(", ")}` : "No institution"}
          </div>
          <button className="secondary" onClick={logout}>
            Sign out
          </button>
        </nav>
        <main>
          {selected === null && !me.is_platform_admin ? (
            <div className="error">Your account is not an active member of any institution.</div>
          ) : (
            children
          )}
        </main>
      </div>
    </SessionContext.Provider>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${statusTone(status)}`}>{status.replaceAll("_", " ").toLowerCase()}</span>;
}

export function AdminOnly({ children }: { children: ReactNode }) {
  const { isAdmin } = useSession();
  return isAdmin ? <>{children}</> : null;
}
