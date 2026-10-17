import { useEffect, useRef, useState } from "react";
import { Icon, type IconName } from "../components/icons";
import { Logo } from "../components/Logo";
import { useAuth } from "../lib/auth";
import { Link } from "../lib/router";

/*
 * Hero media. Add a licensed, silent clip at public/assets/hero.mp4 (and optionally hero.webm)
 * to enable the looping video; otherwise the photograph below is shown. If the photograph cannot
 * load either, the overlay colour alone keeps the hero readable.
 * Photo: Unsplash (Unsplash License) — aerial view of a river through green fields.
 */
const HERO_VIDEO = ["/assets/hero.webm", "/assets/hero.mp4"];
const HERO_PHOTO = "https://images.unsplash.com/photo-1681226298721-88cdb4096e5f?auto=format&fit=crop&w=2400&q=75";

function HeroMedia() {
  const [videoOk, setVideoOk] = useState(true);
  const ref = useRef<HTMLVideoElement>(null);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    // A missing file fails on every <source>; treat that as "no video".
    const last = v.querySelectorAll("source");
    const onErr = () => setVideoOk(false);
    last[last.length - 1]?.addEventListener("error", onErr);
    return () => last[last.length - 1]?.removeEventListener("error", onErr);
  }, []);
  return (
    <div className="absolute inset-0 bg-forest-deep">
      <img src={HERO_PHOTO} alt="" className="absolute inset-0 size-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
      {videoOk && !reduced && (
        <video ref={ref} className="absolute inset-0 size-full object-cover" autoPlay muted loop playsInline preload="metadata" aria-hidden="true">
          {HERO_VIDEO.map((s) => (
            <source key={s} src={s} type={s.endsWith(".webm") ? "video/webm" : "video/mp4"} />
          ))}
        </video>
      )}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(16,38,28,0.55)_0%,rgba(16,38,28,0.25)_38%,rgba(16,38,28,0.82)_100%)]" />
    </div>
  );
}

function PreviewCard() {
  // A faithful miniature of two real screens (harvest safety and produce rerouting), with example values.
  return (
    <div className="hero-rise w-full max-w-[400px] rounded-xl bg-paper/95 p-4 text-charcoal shadow-lift backdrop-blur" style={{ animationDelay: "250ms" }} aria-label="Example of the AGASTYA workspace">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] font-bold">Tomato · North Plot</div>
          <div className="text-[11px] text-muted">Example harvest-safety view</div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-danger-soft px-2 py-0.5 text-[11px] font-semibold text-danger">
          <Icon name="Lock" size={11} strokeWidth={2} /> Restricted
        </span>
      </div>
      <div className="mt-3 grid grid-cols-7 gap-1" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className={`h-7 rounded-sm ${i < 4 ? "bg-danger/15" : i === 4 ? "bg-forest" : "bg-sage-pale"}`} />
        ))}
      </div>
      <div className="mt-1.5 text-[11px] text-muted">Eligible from day 5 under the verified label interval</div>
      <div className="mt-4 border-t border-line pt-3">
        <div className="text-[11px] font-semibold text-muted">Alternative buyers for 600 kg, grade A</div>
        {[["Godavari Fresh Traders", "12 km", 86], ["Mumbai Fresh Link", "152 km", 61]].map(([n, d, s]) => (
          <div key={n as string} className="mt-2 flex items-center gap-3">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sage-pale">
              <div className="h-full rounded-full bg-forest" style={{ width: `${s}%` }} />
            </div>
            <div className="w-40 text-[12px]"><span className="font-semibold">{n}</span> <span className="text-muted">{d}</span></div>
          </div>
        ))}
      </div>
    </div>
  );
}

const MODULES: { icon: IconName; name: string; body: string; fact: string }[] = [
  { icon: "Flower2", name: "Smart pollination", body: "See every flowering window, find beekeepers who serve your district and crop, and book colonies with capacity checked.", fact: "Bookings confirmed by the provider, not assumed" },
  { icon: "ScanLine", name: "Crop health", body: "Photograph a leaf and get the model's reading with its confidence. Unclear results go to an agronomist before anyone acts.", fact: "38 leaf conditions across 14 crops" },
  { icon: "FlaskConical", name: "Harvest safety", body: "Record each spray. Pre-harvest intervals come only from verified label rules, so a countdown is never a guess.", fact: "Missing label data is flagged, never filled in" },
  { icon: "ArrowRightLeft", name: "Produce rerouting", body: "When a buyer cancels, ranked alternatives appear with the reasons and trade-offs. Confirm one and the shipment follows.", fact: "Every destination change kept in history" },
];

export default function Landing() {
  const { user } = useAuth();
  const cta = user ? "/app" : "/login";
  return (
    <div className="bg-cream">
      <section className="relative isolate flex min-h-[100svh] flex-col overflow-hidden text-white">
        <HeroMedia />
        <header className="relative z-10 mx-auto flex w-full max-w-[1240px] items-center justify-between px-5 py-5 sm:px-8">
          <Logo tone="light" />
          <nav className="flex items-center gap-1 sm:gap-3" aria-label="Site">
            <a href="#modules" className="hidden rounded-full px-4 py-2 text-sm font-semibold text-white/85 hover:text-white sm:inline-block">Platform</a>
            <Link to={cta} className="rounded-full border border-white/50 px-4 py-2 text-sm font-semibold hover:bg-white/10">{user ? "Open workspace" : "Sign in"}</Link>
          </nav>
        </header>
        <div className="relative z-10 mx-auto flex w-full max-w-[1240px] flex-1 flex-col justify-end gap-10 px-5 pb-14 sm:px-8 lg:flex-row lg:items-end lg:justify-between lg:pb-20">
          <div className="hero-rise max-w-2xl">
            <h1 className="text-[2.6rem] leading-[1.02] font-extrabold tracking-[-0.035em] sm:text-display">
              Grow Smarter.<br />Harvest Safer.<br />Waste Less.
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-white/85">
              AGASTYA keeps pollination, crop health, spray records and buyer deliveries in one place, so each decision on the farm has a clear next step.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={cta} className="inline-flex h-12 items-center gap-2 rounded-full bg-cream px-7 text-[15px] font-bold text-forest-deep shadow-lift hover:bg-white">
                Explore the platform
              </Link>
              <a href="#modules" className="inline-flex h-12 items-center rounded-full px-5 text-[15px] font-semibold text-white/90 hover:text-white">
                How it works
              </a>
            </div>
          </div>
          <div className="hidden md:block"><PreviewCard /></div>
        </div>
      </section>

      <section id="modules" className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 lg:py-28">
        <div className="max-w-2xl">
          <h2 className="text-[2rem] leading-tight font-extrabold tracking-[-0.025em] text-forest-ink sm:text-[2.5rem]">One crop record, from flower to buyer.</h2>
          <p className="mt-4 text-[17px] text-muted">
            The pollination you book, the leaves you photograph, the sprays you record and the batches you sell all belong to the same crop cycle, so nothing has to be entered twice.
          </p>
        </div>
        <div className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
          {MODULES.map((m) => (
            <article key={m.name} className="flex flex-col bg-paper p-7 lg:p-9">
              <span className="grid size-11 place-items-center rounded-full bg-sage-pale text-forest"><Icon name={m.icon} size={21} /></span>
              <h3 className="mt-5 text-xl font-bold text-forest-ink">{m.name}</h3>
              <p className="mt-2 max-w-md text-[15px] text-charcoal/85">{m.body}</p>
              <p className="mt-auto pt-6 text-[13px] font-semibold text-earth">{m.fact}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-forest-deep text-white">
        <div className="mx-auto flex max-w-[1240px] flex-col items-start justify-between gap-6 px-5 py-14 sm:px-8 md:flex-row md:items-center">
          <p className="max-w-xl text-2xl leading-snug font-bold tracking-[-0.02em]">Farmers, beekeepers, buyers and agronomists each get their own workspace, working from the same records.</p>
          <Link to={cta} className="inline-flex h-12 items-center rounded-full bg-cream px-7 font-bold text-forest-deep hover:bg-white">Get started</Link>
        </div>
      </section>

      <footer className="mx-auto flex max-w-[1240px] flex-col gap-3 px-5 py-8 text-[13px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <Logo size={22} />
        <p>AI-Powered Crop Lifecycle Intelligence. Decision support only — confirm diagnoses and label requirements with qualified advisers.</p>
      </footer>
    </div>
  );
}
