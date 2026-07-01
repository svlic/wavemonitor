import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Route, Switch, Link, useLocation } from "wouter";
import { apiClient, ApiError } from "./api/client";
import { InstrumentList } from "./pages/instruments/InstrumentList";
import { InstrumentCreate } from "./pages/instruments/InstrumentCreate";
import { InstrumentEdit } from "./pages/instruments/InstrumentEdit";
import { Dashboard } from "./pages/dashboard/Dashboard";
import "./styles.css";

type AuthState = "checking" | "authenticated" | "password-required";

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

function LoginGate({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const status = await apiClient.login(password);
      if (status.authenticated) {
        onAuthenticated();
        return;
      }
      setError("密码验证未启用或未通过。");
    } catch (loginError) {
      setError(loginError instanceof ApiError ? loginError.message : "验证失败，请重试。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="auth-layout">
      <form className="panel auth-panel" onSubmit={handleSubmit}>
        <p className="eyebrow">WaveMonitor</p>
        <h1>访问验证</h1>
        <p className="summary">请输入共享访问密码，验证后即可进入监控后台。</p>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div className="form-group">
          <label htmlFor="access-password">访问密码</label>
          <input
            id="access-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </div>
        <button type="submit" className="button primary" disabled={isSubmitting || password.length === 0}>
          {isSubmitting ? "验证中..." : "进入"}
        </button>
      </form>
    </main>
  );
}

function AppShell() {
  return (
    <div className="app-layout">
      <nav className="sidebar" aria-label="主导航">
        <div className="sidebar-header">
          <span className="brand-mark" aria-hidden="true" />
          <h2 className="brand-title">WaveMonitor</h2>
          <p className="brand-tagline">价格与告警监控</p>
        </div>
        <ul className="nav-links">
          <li>
            <NavLink href="/">仪表盘</NavLink>
          </li>
          <li>
            <NavLink href="/instruments">标的管理</NavLink>
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
              <h1>页面未找到</h1>
              <p className="summary">你访问的页面不存在。</p>
              <Link href="/" className="button primary">
                返回仪表盘
              </Link>
            </div>
          </Route>
        </Switch>
      </main>
    </div>
  );
}

export function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    async function loadSession() {
      try {
        const status = await apiClient.getAuthSession(controller.signal);
        setAuthState(status.auth_enabled && !status.authenticated ? "password-required" : "authenticated");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setAuthState("password-required");
      }
    }

    loadSession();
    return () => controller.abort();
  }, []);

  if (authState === "checking") {
    return (
      <main className="auth-layout">
        <div className="panel auth-panel" role="status" aria-live="polite">
          <h1>正在验证访问状态...</h1>
        </div>
      </main>
    );
  }

  if (authState === "password-required") {
    return <LoginGate onAuthenticated={() => setAuthState("authenticated")} />;
  }

  return <AppShell />;
}
