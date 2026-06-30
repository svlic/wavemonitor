import { Route, Switch, Link } from "wouter";
import { InstrumentList } from "./pages/instruments/InstrumentList";
import { InstrumentCreate } from "./pages/instruments/InstrumentCreate";
import { InstrumentEdit } from "./pages/instruments/InstrumentEdit";
import { Dashboard } from "./pages/dashboard/Dashboard";
import "./styles.css";

export function App() {
  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="sidebar-header">
          <h2>WaveMonitor</h2>
        </div>
        <ul className="nav-links">
          <li><Link href="/">Dashboard</Link></li>
          <li><Link href="/instruments">Instruments</Link></li>
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
            <div className="panel">404 - Not Found</div>
          </Route>
        </Switch>
      </main>
    </div>
  );
}
