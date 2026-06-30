import type { ReactNode } from "react";
import { Route, Switch, Link, useLocation } from "wouter";
import { InstrumentList } from "./pages/instruments/InstrumentList";
import { InstrumentCreate } from "./pages/instruments/InstrumentCreate";
import { InstrumentEdit } from "./pages/instruments/InstrumentEdit";
import { Dashboard } from "./pages/dashboard/Dashboard";
import "./styles.css";

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const [location] = useLocation();
  const isActive =
    href === "/"
      ? location === "/"
      : location === href || location.startsWith(`${href}/`);

  return (
    <Link href={href} className={isActive ? "nav-link nav-link--active" : "nav-link"}>
      {children}
    </Link>
  );
}

export function App() {
  return (
    <div className="app-layout">
      <nav className="sidebar" aria-label="Main navigation">
        <div className="sidebar-header">
          <span className="brand-mark" aria-hidden="true" />
          <h2 className="brand-title">WaveMonitor</h2>
          <p className="brand-tagline">Price &amp; alert monitor</p>
        </div>
        <ul className="nav-links">
          <li>
            <NavLink href="/">Dashboard</NavLink>
          </li>
          <li>
            <NavLink href="/instruments">Instruments</NavLink>
          </li>
        </ul>
      </nav>
      <main className="main-content">
        <Switch>
          <Route path="/" component={Dashboard} />
          <Route path="/instruments" component={InstrumentList} />
          <Route path="/instruments/new" component={InstrumentCreate} />
          <Route path="/instruments/:id/edit">
            {params => <InstrumentEdit id={params.id} />}
          </Route>
          <Route>
            <div className="panel panel--centered">
              <p className="eyebrow">404</p>
              <h1>Page not found</h1>
              <p className="summary">The route you requested does not exist.</p>
              <Link href="/" className="button primary">
                Back to Dashboard
              </Link>
            </div>
          </Route>
        </Switch>
      </main>
    </div>
  );
}