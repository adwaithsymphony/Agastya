import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "../components/icons";
import { Logo } from "../components/Logo";
import { Button, Field, Input } from "../components/ui";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Link, Redirect, useNavigate, useSearchParam } from "../lib/router";
import { LanguageSelect } from "../lib/i18n";

type Health = { status: string; database?: { available: boolean; schema_ready: boolean }; setup_hints?: boolean };

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function errorText(err: ApiError): string {
  if (err.status === 401) return "Email or password is incorrect.";
  if (err.status === 403 && err.code === "account_disabled") return err.message;
  if (err.status === 429) return "Too many sign-in attempts. Wait a few minutes and try again.";
  if (err.status === 0) return "Can't reach AGASTYA. Check your connection and try again.";
  if (err.status >= 500) return "AGASTYA is temporarily unavailable. Please try again shortly.";
  return err.message;
}

function safeNext(next: string | null): string {
  return next && next.startsWith("/app") && !next.startsWith("//") ? next : "/app";
}

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const next = useSearchParam("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((v: Health | null) => setHealth(v))
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  if (user) return <Redirect to={safeNext(next)} />;

  const emailError = touched && !EMAIL_RE.test(email.trim()) ? "Enter a valid email address." : undefined;
  const passwordError = touched && !password ? "Enter your password." : undefined;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!EMAIL_RE.test(email.trim()) || !password) return;
    setPending(true);
    setError(null);
    try {
      await login(email.trim(), password);
      // The workspace is chosen from the role the server returns; the browser never decides access.
      navigate(safeNext(next), { replace: true });
    } catch (err) {
      setError(errorText(err as ApiError));
      setPassword("");
      setTouched(false);
    } finally {
      setPending(false);
    }
  };

  const degraded = health?.status === "degraded";

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between gap-4">
          <Link to="/" aria-label="AGASTYA home" className="self-start"><Logo /></Link>
          <LanguageSelect compact />
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="text-title font-bold text-forest-ink">Sign in to AGASTYA</h1>
          <p className="mt-1 text-sm text-muted">Use the email and password your organisation set up for you.</p>

          {degraded && (
            <div role="status" className="mt-6 rounded-lg border border-amber/30 bg-amber-soft px-3.5 py-3 text-sm text-[#5f4210]">
              <p className="font-semibold">AGASTYA isn't fully available right now.</p>
              {health?.setup_hints ? (
                !health.database?.available ? (
                  <p className="mt-1">The server can't reach its database. Check that the database is running and that <code>DATABASE_URL</code> in <code>.env</code> is correct.</p>
                ) : (
                  <p className="mt-1">The database needs migrating. From the <code>backend</code> folder run <code>alembic upgrade head</code>, then refresh this page.</p>
                )
              ) : (
                <p className="mt-1">Please try again in a few minutes.</p>
              )}
            </div>
          )}

          <form onSubmit={submit} className="mt-7 space-y-4" noValidate>
            <Field label="Email" htmlFor="email" error={emailError}>
              <Input
                id="email"
                type="email"
                inputMode="email"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                aria-invalid={!!emailError}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Password" htmlFor="password" error={passwordError}>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  aria-invalid={!!passwordError}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-11"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-muted hover:text-forest"
                >
                  <Icon name={showPassword ? "EyeOff" : "Eye"} size={17} />
                </button>
              </div>
            </Field>
            {error && (
              <div ref={errorRef} tabIndex={-1} role="alert" className="flex items-start gap-2 rounded-md border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger outline-none">
                <Icon name="CircleAlert" size={16} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <Button type="submit" className="w-full" size="lg" loading={pending}>
              {pending ? "Signing in" : "Sign in"}
            </Button>
          </form>
          <p className="mt-6 text-[13px] text-muted">Forgotten your password or need an account? Contact your organisation's AGASTYA administrator.</p>
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-forest-deep lg:block">
        <img src="https://images.unsplash.com/photo-1681226298721-88cdb4096e5f?auto=format&fit=crop&w=1600&q=70" alt="" className="absolute inset-0 size-full object-cover opacity-70" onError={(e) => (e.currentTarget.style.display = "none")} />
        <div className="absolute inset-0 bg-gradient-to-t from-forest-ink/85 via-forest-ink/20 to-transparent" />
        <p className="absolute right-12 bottom-12 left-12 text-3xl leading-tight font-extrabold tracking-[-0.02em] text-white">Grow Smarter.<br />Harvest Safer.<br />Waste Less.</p>
      </div>
    </div>
  );
}
