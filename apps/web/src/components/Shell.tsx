"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, createContext, useContext, useEffect, useState } from "react";

import { getInstitution, setInstitution, useApi } from "@/lib/client";
import { initials, roleLabel, statusLabel, statusTone } from "@/lib/format";
import type { Me, Membership } from "@/lib/types";

import { Icon, type IconName } from "./Icon";

interface Session {
  me: Me;
  membership: Membership | null;
  isAdmin: boolean;
  isTeacher: boolean;
}

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error("useSession must be used inside <Shell>");
  return session;
}

const LINKS: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Pase de lista", icon: "roll" },
  { href: "/attendance", label: "Registros", icon: "clipboard" },
  { href: "/analytics", label: "Analíticas", icon: "chart" },
  { href: "/campuses", label: "Sedes y geocercas", icon: "pin" },
  { href: "/people", label: "Personas", icon: "users" },
];

function Brand() {
  return (
    <Link href="/" className="brand">
      <span className="brand-mark">
        <Icon name="bell" size={20} />
      </span>
      <span className="brand-name">SchoolTrack</span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: me, error } = useApi<Me>("users/me");
  const [selected, setSelected] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!me) return;
    const stored = getInstitution();
    const valid = me.memberships.find((m) => m.institution_id === stored);
    const choice = valid?.institution_id ?? me.memberships[0]?.institution_id ?? null;
    if (choice) setInstitution(choice);
    setSelected(choice);
  }, [me]);

  useEffect(() => setMenuOpen(false), [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  if (error) {
    return (
      <main>
        <div className="error">{error}</div>
      </main>
    );
  }
  if (!me) {
    return (
      <div className="loading" role="status" aria-label="Cargando">
        <div className="spinner" />
      </div>
    );
  }

  const membership = me.memberships.find((m) => m.institution_id === selected) ?? null;
  const session: Session = {
    me,
    membership,
    isAdmin: membership?.roles.includes("SCHOOL_ADMIN") ?? false,
    isTeacher: membership?.roles.includes("TEACHER") ?? false,
  };
  const role = membership ? roleLabel(membership.roles) : me.is_platform_admin ? "Plataforma" : "Sin institución";

  return (
    <SessionContext.Provider value={session}>
      <div className="layout">
        <header className="topbar">
          <Brand />
          <button
            className="icon-button"
            aria-label="Abrir menú"
            aria-expanded={menuOpen}
            aria-controls="sidebar"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" size={24} />
          </button>
        </header>
        <nav
          id="sidebar"
          className="sidebar"
          data-open={menuOpen}
          aria-label="Principal"
        >
          <Brand />
          <div className="nav-group">
            {LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="nav-link"
                aria-current={pathname === link.href ? "page" : undefined}
              >
                <Icon name={link.icon} />
                {link.label}
              </Link>
            ))}
          </div>
          {me.is_platform_admin && (
            <div className="nav-group">
              <span className="nav-caption">Plataforma</span>
              <Link
                href="/institutions"
                className="nav-link"
                aria-current={pathname === "/institutions" ? "page" : undefined}
              >
                <Icon name="building" />
                Instituciones
              </Link>
            </div>
          )}
          <div className="spacer" />
          {me.memberships.length > 1 && (
            <select
              aria-label="Institución"
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
          <div className="account">
            <span className="avatar">{initials(me.full_name)}</span>
            <div className="account-text">
              <div className="account-name">{me.full_name}</div>
              <div className="account-role">
                {role}
                {membership && me.memberships.length === 1 ? `, ${membership.institution_name}` : ""}
              </div>
            </div>
            <button className="icon-button" onClick={logout} aria-label="Cerrar sesión" title="Cerrar sesión">
              <Icon name="logout" />
            </button>
          </div>
        </nav>
        {menuOpen && <div className="backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
        <main>
          <div className="page">
            {selected === null && !me.is_platform_admin ? (
              <div className="error">
                <Icon name="alert" />
                Tu cuenta no pertenece a ninguna institución activa. Pide a la institución que te agregue.
              </div>
            ) : (
              children
            )}
          </div>
        </main>
      </div>
    </SessionContext.Provider>
  );
}

export function PageHead({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${statusTone(status)}`}>{statusLabel(status)}</span>;
}

export function Message({ tone, children }: { tone: "error" | "success" | "notice"; children: ReactNode }) {
  return (
    <div className={tone} role={tone === "error" ? "alert" : "status"}>
      <Icon name={tone === "success" ? "check" : "alert"} size={18} />
      <span>{children}</span>
    </div>
  );
}

export function AdminOnly({ children }: { children: ReactNode }) {
  const { isAdmin } = useSession();
  return isAdmin ? <>{children}</> : null;
}
