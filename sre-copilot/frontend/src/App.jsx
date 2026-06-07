import { useEffect, useState, useRef, useCallback } from "react";

const API          = import.meta.env.VITE_API_URL ?? "";
const WEBHOOK_HOST = "https://sre-webhook-366154347729.us-central1.run.app";

// ── Theme ─────────────────────────────────────────────────────────────────────
const DARK = {
  bg:         "#08080a",
  surface:    "#111113",
  surface2:   "#18181c",
  border:     "#222228",
  text:       "#f0f0f2",
  textSub:    "#6b6b7a",
  textMuted:  "#3a3a4a",
  approve:    "#16a34a",
  approveBg:  "#052e16",
  reject:     "#dc2626",
  rejectBg:   "#2d0a0a",
  codeBg:     "#0d0d10",
  accent:     "#f97316",
  accentDim:  "#431407",
  accentGlow: "rgba(249,115,22,0.15)",
  badge:      "#18181c",
  toggle:     "#f0f0f2",
  toggleBg:   "#222228",
};
const LIGHT = {
  bg:         "#fafafa",
  surface:    "#ffffff",
  surface2:   "#f4f4f5",
  border:     "#e4e4e7",
  text:       "#09090b",
  textSub:    "#71717a",
  textMuted:  "#a1a1aa",
  approve:    "#15803d",
  approveBg:  "#f0fdf4",
  reject:     "#b91c1c",
  rejectBg:   "#fef2f2",
  codeBg:     "#f4f4f5",
  accent:     "#ea580c",
  accentDim:  "#fff7ed",
  accentGlow: "rgba(234,88,12,0.08)",
  badge:      "#f4f4f5",
  toggle:     "#09090b",
  toggleBg:   "#e4e4e7",
};

// ── Shared primitives ─────────────────────────────────────────────────────────

const SEV_LABEL = { AVAILABILITY:"Availability", PERFORMANCE:"Performance", ERROR:"Error", RESOURCE_CONTENTION:"Resource" };

function Badge({ text, t }) {
  return (
    <span style={{
      display:"inline-block", background:t.badge, color:t.textSub,
      border:`1px solid ${t.border}`, fontSize:11, fontWeight:600,
      padding:"2px 8px", borderRadius:4, letterSpacing:"0.04em", textTransform:"uppercase",
    }}>{SEV_LABEL[text] || text}</span>
  );
}

function ConfidenceBar({ score, t }) {
  const pct   = Math.round(score * 100);
  const color = pct >= 80 ? "#16a34a" : pct >= 60 ? "#d97706" : "#dc2626";
  return (
    <div style={{ marginTop:12 }}>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
        <span style={{ fontSize:11, fontWeight:600, color:t.textSub, textTransform:"uppercase", letterSpacing:"0.05em" }}>AI Confidence</span>
        <span style={{ fontSize:13, fontWeight:700, color }}>{pct}%</span>
      </div>
      <div style={{ background:t.surface2, borderRadius:99, height:6, overflow:"hidden" }}>
        <div style={{ width:`${pct}%`, background:color, height:"100%", borderRadius:99, transition:"width 0.8s cubic-bezier(0.4,0,0.2,1)" }} />
      </div>
    </div>
  );
}

function inp(t) {
  return {
    width:"100%", boxSizing:"border-box", background:t.surface2,
    border:`1px solid ${t.border}`, color:t.text, borderRadius:8,
    padding:"10px 12px", fontSize:14, outline:"none", fontFamily:"inherit",
    transition:"border-color 0.15s",
  };
}

// ── Siren indicator — pulsing red "ping" like sonar ───────────────────────────

function SirenDot({ size = 8, color = "#dc2626" }) {
  return (
    <span style={{ position:"relative", display:"inline-flex", alignItems:"center", justifyContent:"center", width:size, height:size, flexShrink:0 }}>
      <span style={{
        position:"absolute", inset:0, borderRadius:"50%",
        background:color, animation:"sirenPing 1.4s ease-out infinite",
      }} />
      <span style={{ width:size, height:size, borderRadius:"50%", background:color, display:"inline-block", boxShadow:`0 0 4px ${color}` }} />
    </span>
  );
}

// ── Logo ──────────────────────────────────────────────────────────────────────

function SparkLogo({ size = 28, showText = true, t }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
      <img src="/logo.png" alt="SPARK" style={{ width:size, height:size, objectFit:"contain" }} />
      {showText && (
        <span style={{ fontWeight:900, fontSize:size * 0.78, letterSpacing:"-0.04em", color:t.text }}>
          SPARK
        </span>
      )}
    </div>
  );
}

// ── FireEyeLoader — animated when agent runs ──────────────────────────────────

function FireEyeLoader({ label = "Agent investigating incident..." }) {
  const [frame, setFrame] = useState(0);
  const hints = [
    "Connecting to Dynatrace MCP...",
    "Querying memory metrics...",
    "Analyzing log patterns...",
    "Correlating with deployments...",
    "Forming diagnosis...",
  ];
  useEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % hints.length), 2100);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", padding:"28px 0 20px", gap:16 }}>
      <div style={{ position:"relative", width:130, height:138 }}>
        {/* Transparent background wrapper so SVG blends with dark surface */}
        <div style={{ position:"relative", width:"100%", height:"100%", background:"transparent" }}>
          <img
            src="/fireineye.svg"
            alt="SPARK agent"
            style={{
              width:"100%", height:"100%", objectFit:"contain",
              animation:"fireFlicker 1.1s ease-in-out infinite alternate",
              display:"block",
            }}
          />
        </div>
        <div style={{
          position:"absolute", inset:0, borderRadius:"50%",
          background:"radial-gradient(circle at 50% 60%, rgba(249,115,22,0.22) 0%, transparent 65%)",
          animation:"fireGlow 1.1s ease-in-out infinite alternate",
          pointerEvents:"none",
        }} />
      </div>
      <div style={{ textAlign:"center" }}>
        <div style={{ fontWeight:700, fontSize:15, marginBottom:6 }}>{label}</div>
        <div style={{ fontSize:13, color:"#f97316", fontFamily:"monospace", animation:"fadeIn 0.3s ease" }} key={frame}>
          {hints[frame]}
        </div>
      </div>
    </div>
  );
}

// ── Navbar ────────────────────────────────────────────────────────────────────

function Navbar({ t, dark, toggleDark, onHome, onConnect, session, onDisconnect, activeIncidents }) {
  return (
    <nav style={{
      padding:"14px 28px", display:"flex", alignItems:"center",
      justifyContent:"space-between", borderBottom:`1px solid ${t.border}`,
      position:"sticky", top:0, background:t.bg, zIndex:50, backdropFilter:"blur(8px)",
    }}>
      <button onClick={onHome} style={{ background:"none", border:"none", cursor:"pointer", padding:0 }}>
        <SparkLogo size={28} showText t={t} />
      </button>

      <div style={{ display:"flex", alignItems:"center", gap:10 }}>
        {/* Active incident siren badge in navbar */}
        {activeIncidents > 0 && (
          <div style={{
            display:"flex", alignItems:"center", gap:6,
            background:"rgba(220,38,38,0.12)", border:"1px solid rgba(220,38,38,0.3)",
            borderRadius:99, padding:"3px 10px",
          }}>
            <SirenDot size={7} color="#dc2626" />
            <span style={{ fontSize:11, fontWeight:700, color:"#dc2626" }}>
              {activeIncidents} ACTIVE
            </span>
          </div>
        )}
        {session && (
          <span style={{
            fontSize:11, fontWeight:600, color:"#16a34a",
            background:"rgba(22,163,74,0.1)", border:"1px solid rgba(22,163,74,0.25)",
            padding:"3px 10px", borderRadius:99,
          }}>
            ● {session.is_demo ? "SANDBOX" : `${session.env_name}.dynatrace.com`}
          </span>
        )}
        <button onClick={toggleDark} style={{
          background:t.toggleBg, color:t.toggle, border:`1px solid ${t.border}`,
          borderRadius:8, padding:"7px 14px", fontSize:13, cursor:"pointer",
        }}>
          {dark ? "☀" : "☾"}
        </button>
        {!session ? (
          <button onClick={onConnect} style={{
            background:t.accent, color:"#fff", border:"none",
            borderRadius:8, padding:"8px 18px", fontSize:13, fontWeight:700, cursor:"pointer",
          }}>
            Connect →
          </button>
        ) : (
          <button onClick={onDisconnect} style={{
            background:"transparent", color:t.textSub, border:`1px solid ${t.border}`,
            borderRadius:8, padding:"8px 14px", fontSize:12, cursor:"pointer",
          }}>
            Disconnect
          </button>
        )}
      </div>
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE 1: HOME
// ─────────────────────────────────────────────────────────────────────────────

const STATS = [
  { value:"80%",    label:"avg MTTR reduction"     },
  { value:"< 60s",  label:"time to resolution"     },
  { value:"5",      label:"real post-mortems tested"},
  { value:"100%",   label:"rust-lang accuracy"      },
];
const FLOW = [
  { icon:"🔔", label:"Dynatrace Alert" },
  { icon:"🧠", label:"Gemini Diagnoses" },
  { icon:"🔥", label:"SPARK Alerts You" },
  { icon:"👤", label:"You Approve"     },
  { icon:"⚡", label:"Auto Rollback"   },
  { icon:"✅", label:"Resolved"        },
];

function HomePage({ t, onConnect, onDemo }) {
  const [hovered, setHovered] = useState(null);

  return (
    <div style={{ background:t.bg, minHeight:"100vh", color:t.text }}>

      {/* Hero */}
      <div style={{ maxWidth:860, margin:"0 auto", padding:"72px 24px 56px", textAlign:"center" }}>
        {/* Pill badge */}
        <div style={{
          display:"inline-flex", alignItems:"center", gap:8,
          background:t.surface, border:`1px solid ${t.border}`,
          borderRadius:99, padding:"5px 16px",
          fontSize:12, fontWeight:600, color:t.textSub, marginBottom:32,
        }}>
          <span style={{ color:"#f97316" }}>🔥</span>
          Gemini 2.5 Flash · Google ADK · Dynatrace MCP · GitLab CI
        </div>

        {/* Big logo */}
        <div style={{ display:"flex", justifyContent:"center", marginBottom:24 }}>
          <div style={{ position:"relative" }}>
            <img
              src="/logo.png"
              alt="SPARK"
              style={{ width:96, height:96, objectFit:"contain", animation:"heroFlame 2s ease-in-out infinite alternate" }}
            />
            <div style={{
              position:"absolute", inset:-12,
              background:"radial-gradient(circle, rgba(249,115,22,0.2) 0%, transparent 70%)",
              animation:"fireGlow 2s ease-in-out infinite alternate",
              pointerEvents:"none",
            }} />
          </div>
        </div>

        <h1 style={{
          fontSize:"clamp(40px, 6.5vw, 72px)", fontWeight:900,
          letterSpacing:"-0.045em", lineHeight:1.05, margin:"0 0 8px",
        }}>
          <span style={{ color:t.accent }}>SPARK</span>
        </h1>
        <h2 style={{
          fontSize:"clamp(20px, 3vw, 32px)", fontWeight:700,
          letterSpacing:"-0.025em", lineHeight:1.2, margin:"0 0 24px",
          color:t.text,
        }}>
          Your incidents resolved before you wake up.
        </h2>

        <p style={{
          fontSize:"clamp(15px, 1.8vw, 18px)", color:t.textSub,
          maxWidth:520, margin:"0 auto 40px", lineHeight:1.75,
        }}>
          SPARK connects to Dynatrace, diagnoses incidents with Gemini AI, and
          coordinates rollbacks via GitLab — with your one-tap approval always in the loop.
        </p>

        {/* CTAs */}
        <div style={{ display:"flex", gap:12, justifyContent:"center", flexWrap:"wrap" }}>
          <button
            onClick={onConnect}
            onMouseEnter={() => setHovered("connect")}
            onMouseLeave={() => setHovered(null)}
            style={{
              background: hovered === "connect"
                ? "linear-gradient(135deg,#fb923c,#f97316)"
                : "linear-gradient(135deg,#f97316,#ea580c)",
              color:"#fff", border:"none", borderRadius:10,
              padding:"14px 32px", fontSize:16, fontWeight:700, cursor:"pointer",
              letterSpacing:"-0.01em", boxShadow:"0 4px 20px rgba(249,115,22,0.35)",
              transition:"all 0.15s",
            }}
          >
            🔥 Connect My Dynatrace →
          </button>
          <button
            onClick={onDemo}
            onMouseEnter={() => setHovered("demo")}
            onMouseLeave={() => setHovered(null)}
            style={{
              background: hovered === "demo" ? t.surface2 : "transparent",
              color:t.text, border:`1px solid ${t.border}`, borderRadius:10,
              padding:"14px 24px", fontSize:16, fontWeight:500, cursor:"pointer",
              transition:"all 0.15s",
            }}
          >
            ▶ Live Demo (no account)
          </button>
        </div>

        {/* Stats grid */}
        <div style={{
          display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(130px, 1fr))",
          gap:12, maxWidth:600, margin:"64px auto 0",
        }}>
          {STATS.map(({ value, label }) => (
            <div key={label} style={{
              background:t.surface, border:`1px solid ${t.border}`,
              borderRadius:12, padding:"20px 14px", textAlign:"center",
            }}>
              <div style={{ fontSize:28, fontWeight:900, letterSpacing:"-0.03em", color:t.accent }}>{value}</div>
              <div style={{ fontSize:11, color:t.textSub, marginTop:4 }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Flow */}
        <div style={{
          display:"flex", alignItems:"center", gap:6, flexWrap:"wrap",
          justifyContent:"center", marginTop:64,
        }}>
          {FLOW.map(({ icon, label }, i) => (
            <span key={label} style={{ display:"contents" }}>
              <div style={{
                background:t.surface, border:`1px solid ${t.border}`,
                borderRadius:10, padding:"9px 14px",
                fontSize:13, fontWeight:500,
                display:"flex", alignItems:"center", gap:6,
              }}>
                <span>{icon}</span><span>{label}</span>
              </div>
              {i < FLOW.length - 1 && (
                <span style={{ color:t.textMuted, fontSize:16, flexShrink:0 }}>→</span>
              )}
            </span>
          ))}
        </div>

        {/* Slack callout */}
        <div style={{
          margin:"56px auto 0", maxWidth:560,
          background:`linear-gradient(135deg, ${t.surface}, ${t.surface2})`,
          border:`1px solid ${t.border}`, borderRadius:14,
          padding:"20px 24px", textAlign:"left",
          display:"flex", gap:14, alignItems:"flex-start",
        }}>
          <span style={{ fontSize:28, flexShrink:0 }}>💬</span>
          <div>
            <div style={{ fontSize:13, fontWeight:700, marginBottom:4 }}>Approve from Slack</div>
            <div style={{ fontSize:13, color:t.textSub, lineHeight:1.65 }}>
              When SPARK diagnoses an incident, your Slack buzzes. One tap — approve or reject.
              Rollback executes automatically.
            </div>
          </div>
        </div>

        {/* Post-mortem benchmark */}
        <div style={{
          margin:"24px auto 0", maxWidth:560,
          background:t.surface, border:`1px solid ${t.border}`,
          borderRadius:14, padding:"20px 24px", textAlign:"left",
        }}>
          <div style={{ fontSize:11, color:t.textSub, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:10 }}>
            Live benchmark — 5 real production post-mortems
          </div>
          <div style={{ fontSize:13, color:t.text, lineHeight:1.75 }}>
            Tested against Cloudflare, PagerDuty, rust-lang, Foursquare.
            Human engineers took <strong>15 min – 17 hours</strong>.
            SPARK: <strong style={{ color:"#16a34a" }}>80% average accuracy</strong>.
            Foursquare MongoDB OOM — agent correctly said <em>don't rollback, fix the index</em>.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE 2: CONNECT
// ─────────────────────────────────────────────────────────────────────────────

function ConnectPage({ t, onBack, onConnected }) {
  const [step,        setStep]      = useState(1);
  const [useOAuth,    setUseOAuth]  = useState(false);
  const [dtUrl,       setDtUrl]     = useState("");
  const [dtToken,     setDtToken]   = useState("");
  const [dtClientId,  setClientId]  = useState("");
  const [dtClientSec, setClientSec] = useState("");
  const [glUrl,       setGlUrl]     = useState("https://gitlab.com");
  const [glProject,   setGlProject] = useState("");
  const [glToken,     setGlToken]   = useState("");
  const [slToken,     setSlToken]   = useState("");
  const [slChannel,   setSlChannel] = useState("");
  const [oauthEnabled, setOauthEnabled] = useState(false);
  const [manualSlack,  setManualSlack]  = useState(false);
  const [slState,     setSlState]   = useState("");      // opaque OAuth handle
  const [slTeam,      setSlTeam]     = useState("");
  const [slChannels,  setSlChannels] = useState(null);   // null = not loaded
  const [slLoadingCh, setSlLoadingCh] = useState(false);
  const [loading,     setLoading]   = useState(false);
  const [error,       setError]     = useState("");

  // Step 1 is valid when URL + appropriate auth fields are filled
  const step1Valid = dtUrl && (useOAuth ? (dtClientId && dtClientSec) : dtToken);

  // Is "Add to Slack" OAuth available on this deployment?
  useEffect(() => {
    fetch(`${API}/slack/oauth/config`)
      .then(r => r.json())
      .then(d => setOauthEnabled(!!d.enabled))
      .catch(() => {});
  }, []);

  // Receive the OAuth result from the popup window
  useEffect(() => {
    const appOrigin = API ? new URL(API).origin : window.location.origin;
    const onMsg = (e) => {
      if (e.origin !== appOrigin) return;   // only trust messages from our own origin
      const d = e.data;
      if (!d || d.type !== "spark_slack_oauth") return;
      if (d.error) { setError(`Slack: ${d.error}`); return; }
      if (d.state) {
        setError(""); setSlState(d.state); setSlTeam(d.team || "your workspace");
        loadChannels(d.state);
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const loadChannels = async (state) => {
    setSlLoadingCh(true);
    try {
      const r = await fetch(`${API}/slack/channels?state=${encodeURIComponent(state)}`);
      const d = await r.json();
      if (r.ok) setSlChannels(d.channels || []);
      else setError(d.error || "Could not load channels");
    } catch { setError("Could not load Slack channels"); }
    finally { setSlLoadingCh(false); }
  };

  const openSlackOAuth = () => {
    setError("");
    window.open(`${API}/slack/oauth/start`, "spark_slack_oauth", "width=640,height=720");
  };

  const resetSlackOAuth = () => {
    setSlState(""); setSlTeam(""); setSlChannels(null); setSlChannel("");
  };

  // Show manual token entry when OAuth is unavailable or the user opts into it
  const showManualSlack = !oauthEnabled || manualSlack;

  const goStep2 = () => {
    if (!dtUrl.startsWith("http")) { setError("Enter a valid URL (https://...)"); return; }
    if (useOAuth) {
      if (!dtClientId || !dtClientSec) { setError("Client ID and Client Secret are required"); return; }
    } else {
      if (!dtToken) { setError("API token is required"); return; }
    }
    setError(""); setStep(2);
  };

  const goStep3 = () => {
    if (!glToken) { setError("GitLab token is required"); return; }
    setError(""); setStep(3);
  };

  const connect = async ({ skip = false } = {}) => {
    const usingOAuth  = !skip && !!slState;
    const slBot       = skip ? "" : (usingOAuth ? "" : slToken.trim());
    const oauthState  = skip ? "" : (usingOAuth ? slState : "");
    const slCh        = skip ? "" : slChannel.trim();

    // Slack is optional, but once a workspace/token is set a channel is required.
    if (!skip && (slBot || oauthState) && !slCh) {
      setError("Pick a Slack channel for incident alerts");
      return;
    }
    setLoading(true); setError("");
    try {
      const dtPart = useOAuth
        ? { dt_url:dtUrl.trim(), dt_client_id:dtClientId.trim(), dt_client_secret:dtClientSec.trim() }
        : { dt_url:dtUrl.trim(), dt_token:dtToken.trim() };
      const body = {
        ...dtPart,
        gl_url:glUrl.trim(), gl_token:glToken.trim(), gl_project_id:glProject.trim(),
        slack_bot_token:slBot, slack_oauth_state:oauthState, slack_channel_id:slCh,
      };
      const r = await fetch(`${API}/connect`, {
        method:"POST",
        headers:{ "Content-Type":"application/json" },
        body:JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) { setError(data.error || "Connection failed"); return; }
      localStorage.setItem("spark_session", JSON.stringify(data));
      onConnected(data);
    } catch { setError("Network error — check your connection"); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ background:t.bg, minHeight:"100vh", color:t.text, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:24 }}>

      {/* Back */}
      <button onClick={onBack} style={{
        position:"absolute", top:24, left:24,
        background:"transparent", color:t.textSub, border:`1px solid ${t.border}`,
        borderRadius:8, padding:"7px 14px", fontSize:13, cursor:"pointer",
        display:"flex", alignItems:"center", gap:6,
      }}>
        ← Back
      </button>

      <div style={{ width:"100%", maxWidth:440 }}>
        {/* Logo */}
        <div style={{ textAlign:"center", marginBottom:32 }}>
          <img src="/logo.png" alt="SPARK" style={{ width:48, height:48, objectFit:"contain", marginBottom:8 }} />
          <div style={{ fontWeight:900, fontSize:22, letterSpacing:"-0.04em" }}>SPARK</div>
        </div>

        {/* Card */}
        <div style={{
          background:t.surface, border:`1px solid ${t.border}`,
          borderRadius:16, padding:"32px 32px 28px",
        }}>
          {/* Progress */}
          <div style={{ display:"flex", gap:6, marginBottom:28 }}>
            {[1,2,3].map(n => (
              <div key={n} style={{ flex:1, height:3, borderRadius:99, background: n <= step ? t.accent : t.border, transition:"background 0.3s" }} />
            ))}
          </div>

          <div style={{ fontSize:11, color:t.textSub, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:6 }}>
            Step {step} of 3
          </div>
          <h2 style={{ margin:"0 0 24px", fontSize:20, fontWeight:800, letterSpacing:"-0.02em" }}>
            {step === 1 ? "Connect Dynatrace" : step === 2 ? "Connect GitLab" : "Connect Slack"}
          </h2>

          {step === 1 ? (
            <>
              <label style={{ display:"block", marginBottom:14 }}>
                <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Environment URL</div>
                <input value={dtUrl} onChange={e => setDtUrl(e.target.value)}
                  placeholder="https://abc12345.apps.dynatrace.com" style={inp(t)} autoFocus />
              </label>

              {/* Auth type toggle */}
              <div style={{ display:"flex", gap:6, marginBottom:14 }}>
                {[["API Token", false], ["OAuth2 Client", true]].map(([label, val]) => (
                  <button key={label} onClick={() => { setUseOAuth(val); setError(""); }}
                    style={{ flex:1, padding:"6px 0", fontSize:12, fontWeight:600, borderRadius:7, cursor:"pointer", border:`1px solid ${useOAuth === val ? t.accent : t.border}`, background: useOAuth === val ? t.accentDim : "transparent", color: useOAuth === val ? t.accent : t.textSub, transition:"all 0.15s" }}>
                    {label}
                  </button>
                ))}
              </div>

              {!useOAuth ? (
                <>
                  <label style={{ display:"block", marginBottom:8 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>API Token</div>
                    <input value={dtToken} onChange={e => setDtToken(e.target.value)}
                      placeholder="dt0s01.xxxx..." type="password" style={inp(t)} />
                  </label>
                  <div style={{ fontSize:11, color:t.textMuted, marginBottom:24, lineHeight:1.7 }}>
                    Settings → Access Tokens → Generate token with scopes:{" "}
                    {["entities.read","metrics.read","logs.read"].map(s => (
                      <code key={s} style={{ background:t.codeBg, border:`1px solid ${t.border}`, padding:"1px 5px", borderRadius:3, marginRight:4, fontSize:11 }}>{s}</code>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <label style={{ display:"block", marginBottom:10 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Client ID</div>
                    <input value={dtClientId} onChange={e => setClientId(e.target.value)}
                      placeholder="dt0s02.XXXXXXXX" style={inp(t)} />
                  </label>
                  <label style={{ display:"block", marginBottom:8 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Client Secret</div>
                    <input value={dtClientSec} onChange={e => setClientSec(e.target.value)}
                      placeholder="dt0s02.XXXXXXXX.YYYYYYYY..." type="password" style={inp(t)} />
                  </label>
                  <div style={{ fontSize:11, color:t.textMuted, marginBottom:24, lineHeight:1.7 }}>
                    DT UI → Settings → OAuth Clients → Create client with scopes:{" "}
                    {["environment-api:problems:read","storage:metrics:read","storage:entities:read"].map(s => (
                      <code key={s} style={{ background:t.codeBg, border:`1px solid ${t.border}`, padding:"1px 5px", borderRadius:3, marginRight:4, fontSize:11 }}>{s}</code>
                    ))}
                  </div>
                </>
              )}
            </>
          ) : step === 2 ? (
            <>
              <label style={{ display:"block", marginBottom:14 }}>
                <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>GitLab URL</div>
                <input value={glUrl} onChange={e => setGlUrl(e.target.value)}
                  placeholder="https://gitlab.com" style={inp(t)} />
              </label>
              <label style={{ display:"block", marginBottom:14 }}>
                <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Project ID</div>
                <input value={glProject} onChange={e => setGlProject(e.target.value)}
                  placeholder="e.g. 82503669" style={inp(t)} autoFocus />
                <div style={{ fontSize:11, color:t.textMuted, marginTop:4 }}>Project → Settings → General → Project ID</div>
              </label>
              <label style={{ display:"block", marginBottom:8 }}>
                <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Personal Access Token</div>
                <input value={glToken} onChange={e => setGlToken(e.target.value)}
                  placeholder="glpat-xxxx..." type="password" style={inp(t)} />
              </label>
              <div style={{ fontSize:11, color:t.textMuted, marginBottom:24, lineHeight:1.7 }}>
                Settings → Access Tokens → scope:{" "}
                <code style={{ background:t.codeBg, padding:"1px 5px", borderRadius:3 }}>api</code>
              </div>
            </>
          ) : (
            <>
              <div style={{
                background:"rgba(96,165,250,0.08)", border:"1px solid rgba(96,165,250,0.22)",
                borderRadius:10, padding:"12px 14px", marginBottom:18,
                display:"flex", gap:10, alignItems:"flex-start",
              }}>
                <span style={{ fontSize:18, flexShrink:0 }}>💬</span>
                <div style={{ fontSize:12, color:t.textSub, lineHeight:1.6 }}>
                  Get incident approvals pushed to <strong style={{ color:t.text }}>your own</strong> Slack.
                  Tap Approve or Reject right from the channel — the rollback runs automatically.
                  <span style={{ color:t.textMuted }}> Optional — you can skip and add it later.</span>
                </div>
              </div>

              {/* OAuth path: one-click connect, then pick a channel */}
              {!showManualSlack && !slState && (
                <>
                  <button onClick={openSlackOAuth} style={{
                    width:"100%", display:"flex", alignItems:"center", justifyContent:"center", gap:10,
                    background:"#4A154B", color:"#fff", border:"none", borderRadius:10,
                    padding:"12px 0", fontSize:15, fontWeight:700, cursor:"pointer", marginBottom:14,
                  }}>
                    <span style={{ fontSize:18 }}>💬</span> Add to Slack
                  </button>
                  <button onClick={() => setManualSlack(true)} style={{
                    width:"100%", background:"transparent", color:t.textSub, border:"none",
                    fontSize:13, cursor:"pointer", textDecoration:"underline", marginBottom:8,
                  }}>
                    or paste a bot token manually
                  </button>
                </>
              )}

              {/* OAuth done: channel picker */}
              {!showManualSlack && slState && (
                <>
                  <div style={{
                    background:t.approveBg, border:`1px solid ${t.approve}44`, color:t.approve,
                    borderRadius:8, padding:"10px 14px", fontSize:13, marginBottom:14,
                    display:"flex", alignItems:"center", gap:8,
                  }}>
                    ✓ Connected to <strong>{slTeam}</strong>
                  </div>
                  <label style={{ display:"block", marginBottom:8 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Alert channel</div>
                    <select value={slChannel} onChange={e => setSlChannel(e.target.value)} style={{ ...inp(t), cursor:"pointer" }}>
                      <option value="">{slLoadingCh ? "Loading channels…" : "Select a channel…"}</option>
                      {(slChannels || []).map(c => (
                        <option key={c.id} value={c.id}>#{c.name}</option>
                      ))}
                    </select>
                  </label>
                  <div style={{ fontSize:11, color:t.textMuted, marginBottom:24, lineHeight:1.7 }}>
                    {slChannels && slChannels.length === 0
                      ? "No channels found — invite the SPARK bot to a channel, then reconnect."
                      : "Don’t see your channel? Invite the SPARK bot to it, then reconnect."}{" "}
                    <button onClick={resetSlackOAuth} style={{ background:"none", border:"none", color:t.accent, cursor:"pointer", fontSize:11, padding:0, textDecoration:"underline" }}>
                      Reconnect
                    </button>
                  </div>
                </>
              )}

              {/* Manual token path */}
              {showManualSlack && (
                <>
                  <label style={{ display:"block", marginBottom:14 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Bot User OAuth Token</div>
                    <input value={slToken} onChange={e => setSlToken(e.target.value)}
                      placeholder="xoxb-..." type="password" style={inp(t)} />
                  </label>
                  <label style={{ display:"block", marginBottom:8 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:t.textSub, marginBottom:6 }}>Channel name or ID</div>
                    <input value={slChannel} onChange={e => setSlChannel(e.target.value)}
                      placeholder="#alerts  or  C0123ABCDEF" style={inp(t)} />
                  </label>
                  <div style={{ fontSize:11, color:t.textMuted, marginBottom:24, lineHeight:1.7 }}>
                    api.slack.com/apps → your app → OAuth &amp; Permissions → bot scopes{" "}
                    {["chat:write","channels:read"].map(s => (
                      <code key={s} style={{ background:t.codeBg, border:`1px solid ${t.border}`, padding:"1px 5px", borderRadius:3, marginRight:4, fontSize:11 }}>{s}</code>
                    ))}
                    · invite the bot to the channel.
                    {oauthEnabled && (
                      <>{" "}<button onClick={() => { setManualSlack(false); setSlToken(""); }} style={{ background:"none", border:"none", color:t.accent, cursor:"pointer", fontSize:11, padding:0, textDecoration:"underline" }}>Use one-click instead</button></>
                    )}
                  </div>
                </>
              )}
            </>
          )}

          {error && (
            <div style={{
              background:t.rejectBg, border:`1px solid ${t.reject}44`,
              color:t.reject, borderRadius:8, padding:"10px 14px",
              fontSize:13, marginBottom:16, lineHeight:1.5,
            }}>
              {error}
            </div>
          )}

          <div style={{ display:"flex", gap:10 }}>
            <button
              onClick={step === 1 ? onBack : () => { setError(""); setStep(step - 1); }}
              style={{ background:"transparent", color:t.textSub, border:`1px solid ${t.border}`, borderRadius:8, padding:"11px 18px", fontSize:14, cursor:"pointer" }}
            >
              {step === 1 ? "Cancel" : "← Back"}
            </button>
            <button
              onClick={step === 1 ? goStep2 : step === 2 ? goStep3 : () => connect()}
              disabled={loading || (step === 1 ? !step1Valid : step === 2 ? !glToken : false)}
              style={{
                flex:1, background:t.accent, color:"#fff", border:"none", borderRadius:8,
                padding:"11px 0", fontSize:14, fontWeight:700,
                cursor:(loading || (step === 1 ? !step1Valid : step === 2 ? !glToken : false)) ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Connecting..." : step === 1 ? "Next → GitLab" : step === 2 ? "Next → Slack" : "Finish & Connect →"}
            </button>
          </div>

          {/* Skip Slack — only on the optional final step */}
          {step === 3 && !loading && (
            <button
              onClick={() => connect({ skip: true })}
              style={{
                width:"100%", marginTop:12, background:"transparent", color:t.textSub,
                border:"none", fontSize:13, cursor:"pointer", textDecoration:"underline",
              }}
            >
              Skip Slack for now →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE 3: DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────

function AgentStepsCard({ incident, t }) {
  const startRef = useRef(incident.created_at ? new Date(incident.created_at) : new Date());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  const steps = incident.steps || [];
  return (
    <div style={{ background:t.surface, border:`1px solid ${t.border}`, borderRadius:14, overflow:"hidden", marginBottom:16 }}>
      {/* Fire animation area — transparent bg so SVG blends cleanly */}
      <div style={{
        background:t.surface2,
        borderBottom:`1px solid ${t.border}`,
        padding:"4px 0 0",
      }}>
        <FireEyeLoader label="Agent investigating incident..." />
      </div>

      {/* Steps log */}
      <div style={{ padding:"20px 24px" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
          <span style={{ fontWeight:700, fontSize:14, color:t.text }}>Investigation log</span>
          <span style={{ fontFamily:"monospace", fontSize:12, color:t.textMuted }}>{elapsed}s</span>
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
          {steps.map((step, i) => (
            <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:10, fontSize:13 }}>
              <span style={{ color:"#16a34a", fontFamily:"monospace", width:14, flexShrink:0 }}>✓</span>
              <span style={{ color:t.text }}>{step.label}</span>
            </div>
          ))}
          {steps.length === 0 && (
            <div style={{ color:t.textMuted, fontSize:13, fontStyle:"italic" }}>Starting investigation...</div>
          )}
        </div>
      </div>
    </div>
  );
}

function ExecutingCard({ incident, t }) {
  const approvedAt = useRef(incident.decided_at ? new Date(incident.decided_at) : new Date());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - approvedAt.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  const cutoff = incident.decided_at ? new Date(incident.decided_at) : new Date(0);
  const postSteps = (incident.steps || []).filter(s => new Date(s.ts) > cutoff);
  return (
    <div style={{ background:t.surface, border:`1px solid ${t.approve}44`, borderRadius:14, padding:"24px 28px", marginBottom:16 }}>
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:14 }}>
        <div style={{ width:8, height:8, borderRadius:"50%", background:t.approve, boxShadow:`0 0 6px ${t.approve}`, animation:"pulse 1.5s infinite" }} />
        <span style={{ fontWeight:700, fontSize:15, color:t.approve }}>Executing rollback...</span>
        <span style={{ marginLeft:"auto", fontFamily:"monospace", fontSize:12, color:t.textMuted }}>+{elapsed}s</span>
      </div>
      <div style={{ fontSize:13, color:t.textSub, marginBottom:14 }}>
        {incident.summary} — rolling back to{" "}
        <code style={{ background:t.codeBg, padding:"1px 6px", borderRadius:3 }}>{incident.rollback_version}</code>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
        {postSteps.map((s, i) => (
          <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:10, fontSize:13 }}>
            <span style={{ color:"#16a34a", fontFamily:"monospace", width:14 }}>✓</span>
            <span>{s.label}</span>
          </div>
        ))}
        <div style={{ display:"flex", alignItems:"center", gap:10, fontSize:13 }}>
          <span style={{ color:t.approve, animation:"spin 1.2s linear infinite", display:"inline-block", fontFamily:"monospace", width:14 }}>⟳</span>
          <span style={{ color:t.textSub }}>Monitoring recovery metrics...</span>
        </div>
      </div>
    </div>
  );
}

function DoneOverlay({ incident, t, onClose }) {
  const secs = incident.resolved_at && incident.created_at
    ? Math.round((new Date(incident.resolved_at) - new Date(incident.created_at)) / 1000)
    : null;

  const allSteps = incident.steps || [];
  const keySteps = allSteps.slice(-6); // last 6 steps for timeline

  return (
    <div style={{
      position:"fixed", inset:0, background:"rgba(0,0,0,0.96)", zIndex:200,
      display:"flex", alignItems:"flex-start", justifyContent:"center",
      padding:"20px 16px", overflowY:"auto", animation:"fadeIn 0.3s ease",
    }}>
      <div style={{
        background:t.surface, border:`1px solid ${t.border}`,
        borderRadius:20, padding:"40px 36px", maxWidth:580, width:"100%",
        marginTop:"auto", marginBottom:"auto",
      }}>
        {/* Header */}
        <div style={{ textAlign:"center", marginBottom:28 }}>
          <div style={{ position:"relative", display:"inline-block", marginBottom:16 }}>
            <img src="/logo.png" alt="SPARK"
              style={{ width:80, height:80, objectFit:"contain", animation:"popIn 0.5s cubic-bezier(0.175,0.885,0.32,1.275)" }} />
            <div style={{ position:"absolute", inset:-16, background:"radial-gradient(circle, rgba(249,115,22,0.3) 0%, transparent 70%)", pointerEvents:"none" }} />
          </div>
          <h2 style={{ margin:"0 0 6px", fontSize:28, fontWeight:900, letterSpacing:"-0.03em" }}>
            Incident Resolved 🔥
          </h2>
          {secs !== null && (
            <div style={{ fontSize:64, fontWeight:900, letterSpacing:"-0.05em", color:t.accent, lineHeight:1, margin:"4px 0 8px" }}>
              {secs}s
            </div>
          )}
          <div style={{ fontSize:13, color:t.textSub }}>Total time from detection to resolution</div>
        </div>

        {/* SPARK vs Manual comparison */}
        {secs !== null && (
          <div style={{ display:"flex", gap:10, marginBottom:28 }}>
            <div style={{ flex:1, background:t.rejectBg, border:`1px solid ${t.reject}33`, borderRadius:12, padding:"14px 18px", textAlign:"center" }}>
              <div style={{ fontSize:10, color:t.textMuted, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:4 }}>Manual avg</div>
              <div style={{ fontSize:26, fontWeight:900, color:t.reject }}>~45 min</div>
            </div>
            <div style={{ display:"flex", alignItems:"center", color:t.textMuted, fontSize:18 }}>vs</div>
            <div style={{ flex:1, background:t.approveBg, border:`1px solid ${t.approve}44`, borderRadius:12, padding:"14px 18px", textAlign:"center" }}>
              <div style={{ fontSize:10, color:t.textMuted, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:4 }}>SPARK</div>
              <div style={{ fontSize:26, fontWeight:900, color:"#16a34a" }}>{secs}s</div>
            </div>
          </div>
        )}

        {/* Divider */}
        <div style={{ borderTop:`1px solid ${t.border}`, margin:"0 0 24px" }} />

        {/* Summary sections */}
        <div style={{ display:"flex", flexDirection:"column", gap:18 }}>

          {/* What happened */}
          <div style={{ background:t.surface2, borderRadius:12, padding:"16px 18px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:t.textSub, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:8 }}>
              📋 What happened
            </div>
            <div style={{ fontSize:14, color:t.text, lineHeight:1.65 }}>{incident.summary}</div>
          </div>

          {/* Root cause */}
          <div style={{ background:t.surface2, borderRadius:12, padding:"16px 18px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:t.textSub, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:8 }}>
              🔍 Root cause identified
            </div>
            <div style={{ fontSize:13, color:t.text, lineHeight:1.7, marginBottom:10 }}>{incident.root_cause}</div>
            {incident.confidence_score && (
              <div style={{ display:"inline-flex", alignItems:"center", gap:6,
                background:"rgba(22,163,74,0.12)", border:"1px solid rgba(22,163,74,0.3)",
                borderRadius:99, padding:"2px 10px", fontSize:11, fontWeight:700, color:"#16a34a" }}>
                ✓ AI Confidence: {Math.round(incident.confidence_score * 100)}%
              </div>
            )}
          </div>

          {/* Action taken */}
          <div style={{ background:t.surface2, borderRadius:12, padding:"16px 18px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:t.textSub, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:8 }}>
              ⚡ Action taken
            </div>
            <div style={{ fontSize:13, color:t.text, lineHeight:1.7, marginBottom:10 }}>{incident.recommended_action}</div>
            {incident.rollback_version && (
              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                <span style={{ fontSize:12, color:t.textSub }}>Rolled back to</span>
                <code style={{ background:t.codeBg, border:`1px solid ${t.border}`, color:t.accent, fontSize:12, padding:"2px 8px", borderRadius:4, fontWeight:700 }}>
                  {incident.rollback_version}
                </code>
              </div>
            )}
          </div>

          {/* Timeline */}
          {keySteps.length > 0 && (
            <div style={{ background:t.surface2, borderRadius:12, padding:"16px 18px" }}>
              <div style={{ fontSize:11, fontWeight:700, color:t.textSub, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:12 }}>
                🕐 Resolution timeline
              </div>
              <div style={{ display:"flex", flexDirection:"column", gap:7 }}>
                {keySteps.map((step, i) => (
                  <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:10, fontSize:12 }}>
                    <span style={{ color:"#16a34a", fontFamily:"monospace", flexShrink:0, marginTop:1 }}>✓</span>
                    <span style={{ color:t.text, lineHeight:1.5 }}>{step.label}</span>
                    <span style={{ color:t.textMuted, fontSize:11, marginLeft:"auto", flexShrink:0, fontFamily:"monospace" }}>
                      {new Date(step.ts).toLocaleTimeString([], { hour:"2-digit", minute:"2-digit", second:"2-digit" })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* GitLab pipeline link */}
        {incident.pipeline_url && (
          <a href={incident.pipeline_url} target="_blank" rel="noopener noreferrer"
            style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:6,
              marginTop:20, fontSize:13, color:t.accent, textDecoration:"none", fontWeight:600 }}>
            View GitLab Pipeline →
          </a>
        )}

        <button onClick={onClose} style={{
          width:"100%", marginTop:20, background:t.surface2, color:t.text,
          border:`1px solid ${t.border}`, borderRadius:10,
          padding:"12px 0", fontSize:14, fontWeight:600, cursor:"pointer",
        }}>
          Back to Dashboard
        </button>
      </div>
    </div>
  );
}

// ── Waiting dots animation ─────────────────────────────────────────────────

function WaitingDots() {
  return (
    <span style={{ display:"inline-flex", gap:3, alignItems:"center", marginLeft:4 }}>
      {[0,1,2].map(i => (
        <span key={i} style={{
          width:5, height:5, borderRadius:"50%", background:"#60a5fa",
          display:"inline-block",
          animation:`waitDot 1.4s ease-in-out ${i * 0.16}s infinite`,
        }} />
      ))}
    </span>
  );
}

// ── Flow step tracker ──────────────────────────────────────────────────────

function FlowTracker({ steps, t }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:0, marginBottom:20 }}>
      {steps.map((s, i) => (
        <span key={i} style={{ display:"contents" }}>
          <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:4, flex: i < steps.length-1 ? "0 0 auto" : 1 }}>
            <div style={{
              width:28, height:28, borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:12, fontWeight:700,
              background: s.done ? "#16a34a" : s.active ? t.accent : t.surface2,
              color: (s.done || s.active) ? "#fff" : t.textMuted,
              border: s.active ? `2px solid ${t.accent}` : "2px solid transparent",
              boxShadow: s.active ? `0 0 10px ${t.accentGlow}` : "none",
              transition:"all 0.3s",
            }}>
              {s.done ? "✓" : i + 1}
            </div>
            <span style={{ fontSize:10, fontWeight:600, color: s.done ? "#16a34a" : s.active ? t.accent : t.textMuted, textAlign:"center", whiteSpace:"nowrap" }}>
              {s.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div style={{ flex:1, height:2, background: s.done ? "#16a34a" : t.border, margin:"0 4px 18px", transition:"background 0.5s" }} />
          )}
        </span>
      ))}
    </div>
  );
}

// ── IncidentCard — full state machine ─────────────────────────────────────

function IncidentCard({ incident, onDecide, t }) {
  const [loading, setLoading] = useState(false);
  const [reason,  setReason]  = useState("");

  if (incident.status === "investigating") return <AgentStepsCard incident={incident} t={t} />;
  if (incident.decision === "approved" && incident.status !== "resolved" && incident.status !== "rejected") {
    return <ExecutingCard incident={incident} t={t} />;
  }

  const decided    = incident.decision != null;
  const isApproved = incident.decision === "approved";
  const isRejected = incident.decision === "rejected";
  const awaitingDecision = !decided && incident.status === "awaiting_decision";

  const decide = async (decision) => {
    setLoading(true);
    await fetch(`${API}/incidents/${incident.incident_id}/decide`, {
      method:"POST", headers:{ "Content-Type":"application/json" },
      body:JSON.stringify({ decision, reason, engineer:"on-call" }),
    });
    setLoading(false); onDecide();
  };

  // Flow steps
  const flowSteps = [
    { label:"Detected",    done: true },
    { label:"Diagnosed",   done: true },
    { label:"Admin review", done: decided, active: awaitingDecision },
    { label:"Rollback",    done: isApproved && incident.status === "resolved", active: false },
    { label:"Resolved",    done: incident.status === "resolved" },
  ];

  return (
    <div style={{
      background:t.surface,
      border:`1px solid ${decided ? (isApproved ? "#16a34a44" : isRejected ? "#dc262644" : t.border) : t.border}`,
      borderRadius:14, padding:"24px 28px", marginBottom:16,
    }}>
      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
        <div style={{ display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>
          {incident.severity && <Badge text={incident.severity} t={t} />}
          <h2 style={{ color:t.text, margin:0, fontSize:16, fontWeight:700, lineHeight:1.4 }}>
            {incident.summary}
          </h2>
        </div>
        {decided && (
          <span style={{
            background: isApproved ? t.approveBg : t.rejectBg,
            color: isApproved ? t.approve : t.reject,
            border:`1px solid ${isApproved ? t.approve + "44" : t.reject + "44"}`,
            padding:"3px 12px", borderRadius:99, fontSize:12, fontWeight:600, flexShrink:0, marginLeft:12,
          }}>
            {isApproved ? "✓ Approved" : "✗ Rejected"}
          </span>
        )}
      </div>

      <p style={{ color:t.textMuted, fontSize:11, margin:"0 0 20px", fontFamily:"monospace" }}>
        {incident.incident_id} · {new Date(incident.created_at).toLocaleTimeString()}
      </p>

      {/* Flow tracker */}
      <FlowTracker steps={flowSteps} t={t} />

      {/* Root cause */}
      <div style={{ marginBottom:12 }}>
        <div style={{ fontSize:11, color:t.textSub, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>Root Cause</div>
        <p style={{ color:t.text, margin:0, lineHeight:1.7, fontSize:14 }}>{incident.root_cause}</p>
        <ConfidenceBar score={incident.confidence_score || 0} t={t} />
      </div>

      <div style={{ borderTop:`1px solid ${t.border}`, margin:"20px 0" }} />

      {/* Recommended action */}
      <div style={{ marginBottom:20 }}>
        <div style={{ fontSize:11, color:t.textSub, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>Recommended Action</div>
        <p style={{ color:t.text, margin:0, lineHeight:1.7, fontSize:14 }}>{incident.recommended_action}</p>
        {incident.rollback_version && (
          <div style={{ marginTop:10, display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ color:t.textSub, fontSize:12 }}>Rollback target:</span>
            <code style={{ background:t.codeBg, border:`1px solid ${t.border}`, color:t.accent, fontSize:12, padding:"2px 8px", borderRadius:4, fontWeight:700 }}>
              {incident.rollback_version}
            </code>
          </div>
        )}
      </div>

      {/* Awaiting admin decision — "Sent to admin" state */}
      {awaitingDecision && (
        <div>
          {/* Slack sent banner */}
          <div style={{
            background:"rgba(96,165,250,0.08)", border:"1px solid rgba(96,165,250,0.25)",
            borderRadius:12, padding:"14px 18px", marginBottom:16,
            display:"flex", alignItems:"center", gap:12,
          }}>
            <span style={{ fontSize:22, flexShrink:0 }}>💬</span>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:13, fontWeight:700, color:"#60a5fa", marginBottom:2 }}>
                Approval request sent to admin via Slack
              </div>
              <div style={{ fontSize:12, color:t.textSub }}>
                Waiting for admin response<WaitingDots />
              </div>
            </div>
            <div style={{ position:"relative", width:10, height:10, flexShrink:0 }}>
              <span style={{ position:"absolute", inset:0, borderRadius:"50%", background:"#60a5fa", animation:"sirenPing 1.6s ease-out infinite" }} />
              <span style={{ width:10, height:10, borderRadius:"50%", background:"#60a5fa", display:"inline-block" }} />
            </div>
          </div>

          {/* Divider with label */}
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:14 }}>
            <div style={{ flex:1, height:1, background:t.border }} />
            <span style={{ fontSize:11, color:t.textMuted, fontWeight:600 }}>OR APPROVE DIRECTLY</span>
            <div style={{ flex:1, height:1, background:t.border }} />
          </div>

          {/* Direct approve/reject buttons */}
          <textarea
            placeholder="Optional note (e.g. 'confirmed with dev team')"
            value={reason} onChange={e => setReason(e.target.value)}
            style={{ width:"100%", background:t.surface2, border:`1px solid ${t.border}`, color:t.text, borderRadius:8, padding:"10px 12px", fontSize:13, marginBottom:10, resize:"vertical", minHeight:48, boxSizing:"border-box", outline:"none", fontFamily:"inherit", lineHeight:1.5 }}
          />
          <div style={{ display:"flex", gap:10 }}>
            <button onClick={() => decide("approved")} disabled={loading} style={{
              flex:1, background:`linear-gradient(135deg,#16a34a,#15803d)`, color:"#fff", border:"none",
              borderRadius:8, padding:"12px 0", fontSize:14, fontWeight:700,
              cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1,
              boxShadow:"0 2px 12px rgba(22,163,74,0.3)",
            }}>
              {loading ? "Processing…" : "✓  Approve Rollback"}
            </button>
            <button onClick={() => decide("rejected")} disabled={loading} style={{
              background:"transparent", color:t.reject,
              border:`1px solid ${t.reject}55`, borderRadius:8,
              padding:"12px 18px", fontSize:14, fontWeight:600,
              cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1,
            }}>
              ✗
            </button>
          </div>
        </div>
      )}

      {/* Already decided */}
      {decided && (
        <div style={{ background:t.surface2, borderRadius:8, padding:"10px 14px", fontSize:13, color:t.textSub }}>
          {isApproved ? "✓ Approved" : "✗ Rejected"} at {new Date(incident.decided_at).toLocaleTimeString()} by {incident.decided_by}
          {incident.reason && <span style={{ color:t.text }}> — "{incident.reason}"</span>}
        </div>
      )}
    </div>
  );
}

function ServicesPanel({ services, isDemo, t }) {
  if (!services || services.length === 0) return null;
  return (
    <div style={{ background:t.surface, border:`1px solid ${t.border}`, borderRadius:12, padding:"18px 22px", marginBottom:20 }}>
      <div style={{ fontSize:11, fontWeight:700, color:t.textSub, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:12, display:"flex", alignItems:"center", gap:8 }}>
        <span>Monitored Services</span>
        {isDemo && (
          <span style={{ background:t.accentDim, color:t.accent, border:`1px solid ${t.accent}33`, fontSize:10, padding:"1px 7px", borderRadius:99, fontWeight:700 }}>DEMO</span>
        )}
      </div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(200px, 1fr))", gap:8 }}>
        {services.map((svc, i) => (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:8, background:t.surface2, borderRadius:8, padding:"8px 12px" }}>
            <span style={{ color:"#16a34a", fontSize:8 }}>●</span>
            <span style={{ fontSize:13, fontWeight:500, color:t.text }}>{svc.name}</span>
            {svc.type && <span style={{ fontSize:11, color:t.textMuted, marginLeft:"auto" }}>{svc.type}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function DashboardPage({ t, session, incidents, onSimulate, simulating, doneInc, onCloseDone }) {
  const pending  = incidents.filter(i => i.decision == null && i.status !== "rejected");
  const resolved = incidents.filter(i => i.decision != null || i.status === "resolved" || i.status === "rejected");
  const activeCount = pending.filter(i => i.status !== "resolved").length;

  return (
    <div style={{ background:t.bg, minHeight:"100vh", color:t.text }}>
      {doneInc && <DoneOverlay incident={doneInc} t={t} onClose={onCloseDone} />}

      {/* Session banner */}
      {session && (
        <div style={{
          background: session.is_demo
            ? `linear-gradient(90deg, ${t.accentDim}, ${t.surface2})`
            : `linear-gradient(90deg, rgba(22,163,74,0.08), ${t.surface2})`,
          borderBottom:`1px solid ${t.border}`,
          padding:"10px 28px", display:"flex", alignItems:"center", gap:12, flexWrap:"wrap",
        }}>
          <div style={{ width:7, height:7, borderRadius:"50%", background:"#16a34a", boxShadow:"0 0 5px #16a34a", flexShrink:0 }} />
          <span style={{ fontSize:13, fontWeight:600, color:t.text }}>
            {session.is_demo ? "demo.apps.dynatrace.com" : `${session.env_name}.apps.dynatrace.com`}
          </span>
          {session.is_demo && (
            <span style={{ background:t.accentDim, color:t.accent, border:`1px solid ${t.accent}44`, fontSize:10, padding:"1px 8px", borderRadius:99, fontWeight:700, letterSpacing:"0.04em" }}>SANDBOX</span>
          )}
          {session.services_count > 0 && <span style={{ fontSize:12, color:t.textSub }}>· {session.services_count} services monitored</span>}
          {session.project_name && <span style={{ fontSize:12, color:t.textSub }}>· {session.project_name}</span>}
          <span style={{ fontSize:12, color:t.textSub }}>· @{session.gl_username}</span>
          {session.slack_connected && (
            <span style={{ fontSize:12, color:t.textSub, display:"inline-flex", alignItems:"center", gap:4 }}>
              · 💬 {session.slack_channel_name ? `#${session.slack_channel_name}` : "Slack"}
              {session.slack_team ? ` · ${session.slack_team}` : ""}
            </span>
          )}

          <div style={{ marginLeft:"auto", display:"flex", gap:8, alignItems:"center" }}>
            {/* Siren indicator when there are active incidents */}
            {activeCount > 0 && (
              <div style={{ display:"flex", alignItems:"center", gap:6, marginRight:4 }}>
                <SirenDot size={8} color="#dc2626" />
                <span style={{ fontSize:11, fontWeight:700, color:"#dc2626" }}>{activeCount} incident{activeCount > 1 ? "s" : ""}</span>
              </div>
            )}
            <button onClick={onSimulate} disabled={simulating} style={{
              background:`linear-gradient(135deg,${t.accent},#ea580c)`, color:"#fff", border:"none",
              borderRadius:7, padding:"6px 16px", fontSize:12, fontWeight:700,
              cursor: simulating ? "not-allowed" : "pointer", opacity: simulating ? 0.6 : 1,
              boxShadow:"0 2px 10px rgba(249,115,22,0.3)",
            }}>
              {simulating ? "⚡ Firing..." : "⚡ Simulate Incident"}
            </button>
          </div>
        </div>
      )}

      {/* Webhook URL */}
      {session && (
        <details style={{ borderBottom:`1px solid ${t.border}`, padding:"0 28px" }}>
          <summary style={{ cursor:"pointer", fontSize:12, color:t.textSub, padding:"8px 0", userSelect:"none" }}>
            ⚙ Webhook URL for Dynatrace real alerts
          </summary>
          <div style={{ padding:"10px 0 14px" }}>
            <code style={{ fontSize:12, background:t.codeBg, border:`1px solid ${t.border}`, borderRadius:6, padding:"8px 12px", display:"block", wordBreak:"break-all", color:t.text }}>
              {`${WEBHOOK_HOST}/dynatrace/webhook?session=${session.session_id}`}
            </code>
            <div style={{ fontSize:11, color:t.textMuted, marginTop:6 }}>
              Dynatrace → Settings → Integrations → Problem Notifications → Custom Integration
            </div>
          </div>
        </details>
      )}

      {/* Main content */}
      <div style={{ maxWidth:720, margin:"0 auto", padding:"28px 20px" }}>
        {session && incidents.length === 0 && (
          <>
            <ServicesPanel services={session.services} isDemo={session.is_demo} t={t} />
            <div style={{
              background:t.surface, border:`2px dashed ${t.border}`,
              borderRadius:14, padding:"40px 24px", textAlign:"center",
            }}>
              <img src="/logo.png" alt="SPARK" style={{ width:56, height:56, objectFit:"contain", marginBottom:12, opacity:0.6 }} />
              <p style={{ fontSize:15, fontWeight:700, margin:"0 0 6px", color:t.text }}>No active incidents</p>
              <p style={{ fontSize:13, color:t.textSub, margin:"0 0 20px" }}>
                Simulate a memory-leak incident to see the full agent flow in ~30 seconds.
              </p>
              <button onClick={onSimulate} disabled={simulating} style={{
                background:`linear-gradient(135deg,${t.accent},#ea580c)`, color:"#fff", border:"none",
                borderRadius:9, padding:"12px 28px", fontSize:14, fontWeight:700,
                cursor: simulating ? "not-allowed" : "pointer", opacity: simulating ? 0.6 : 1,
                boxShadow:"0 4px 16px rgba(249,115,22,0.3)",
              }}>
                {simulating ? "⚡ Firing..." : "⚡ Simulate Incident"}
              </button>
            </div>
          </>
        )}

        {pending.filter(i => i.status !== "resolved").length > 0 && (
          <>
            <div style={{ fontSize:11, fontWeight:700, color:t.reject, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:14, display:"flex", alignItems:"center", gap:8 }}>
              <SirenDot size={7} color="#dc2626" />
              Active Incidents
            </div>
            {pending.filter(i => i.status !== "resolved").map(i => (
              <IncidentCard key={i.incident_id} incident={i} onDecide={() => {}} t={t} />
            ))}
          </>
        )}

        {resolved.length > 0 && (
          <>
            <div style={{ fontSize:11, fontWeight:700, color:t.textMuted, textTransform:"uppercase", letterSpacing:"0.08em", margin:"28px 0 14px", display:"flex", alignItems:"center", gap:8 }}>
              <span style={{ width:6, height:6, borderRadius:"50%", background:t.textMuted, display:"inline-block" }} />
              Resolved
            </div>
            {resolved.map(i => (
              <IncidentCard key={i.incident_id} incident={i} onDecide={() => {}} t={t} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ROOT APP — with URL routing
// ─────────────────────────────────────────────────────────────────────────────

export default function App() {
  const [dark,       setDark]       = useState(true);
  const [page,       setPage]       = useState("home");   // "home" | "connect" | "dashboard"
  const [session,    setSession]    = useState(null);
  const [incidents,  setIncidents]  = useState([]);
  const [simulating, setSimulating] = useState(false);
  const [doneInc,    setDoneInc]    = useState(null);
  const seenResolved = useRef(new Set());
  const didInit = useRef(false);

  const t = dark ? DARK : LIGHT;

  // navigate: updates both React state and URL
  const navigate = useCallback((p) => {
    const urls = { home:"/", connect:"/connect", dashboard:"/dashboard" };
    const target = urls[p] || "/";
    if (window.location.pathname !== target) {
      window.history.pushState({ page: p }, "", target);
    }
    setPage(p);
  }, []);

  const startDemo = useCallback(async () => {
    try {
      const r = await fetch(`${API}/demo`, { method:"POST" });
      const data = await r.json();
      if (!r.ok) {
        console.error("Demo start failed:", data);
        alert(`Demo failed: ${data.error || r.status}. Try refreshing.`);
        return;
      }
      localStorage.setItem("spark_session", JSON.stringify(data));
      setSession(data);
      window.history.pushState({ page:"dashboard" }, "", "/dashboard");
      setPage("dashboard");
    } catch (e) {
      console.error("Demo start failed:", e);
      alert("Could not reach the server. Check your connection and try again.");
    }
  }, []);

  // Initialise page from URL (runs once on mount)
  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;

    const path = window.location.pathname;

    const restoreSession = async () => {
      try {
        const saved = localStorage.getItem("spark_session");
        if (!saved) return false;
        const parsed = JSON.parse(saved);
        const r = await fetch(`${API}/sessions/${parsed.session_id}`);
        if (r.ok) {
          setSession(parsed);
          return true;
        }
        localStorage.removeItem("spark_session");
      } catch {}
      return false;
    };

    const init = async () => {
      if (path === "/demo") {
        // /demo always starts a fresh sandbox session
        await startDemo();
      } else if (path === "/dashboard") {
        const hasSession = await restoreSession();
        if (!hasSession) {
          window.history.replaceState({}, "", "/");
          setPage("home");
        } else {
          setPage("dashboard");
        }
      } else if (path === "/connect") {
        setPage("connect");
      } else {
        // "/" — try silent session restore, go to dashboard if found
        const hasSession = await restoreSession();
        if (hasSession) {
          window.history.replaceState({ page:"dashboard" }, "", "/dashboard");
          setPage("dashboard");
        }
        // else stay on home
      }
    };
    init();
  }, [startDemo]);

  // Keep URL in sync whenever page changes (after init)
  useEffect(() => {
    if (!didInit.current) return;
    const urls = { home:"/", connect:"/connect", dashboard:"/dashboard" };
    const target = urls[page] || "/";
    if (window.location.pathname !== target) {
      window.history.pushState({ page }, "", target);
    }
  }, [page]);

  // Handle browser back / forward
  useEffect(() => {
    const onPop = (e) => {
      const p = window.location.pathname;
      if (p === "/") setPage("home");
      else if (p === "/connect") setPage("connect");
      else if (p === "/dashboard") { if (session) setPage("dashboard"); else { window.history.replaceState({}, "", "/"); setPage("home"); } }
      else if (p === "/demo") startDemo();
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [session, startDemo]);

  const fetchIncidents = useCallback(async (sid) => {
    try {
      const url = sid ? `${API}/incidents?session=${sid}` : `${API}/incidents`;
      const r   = await fetch(url);
      if (!r.ok) return;
      const data = await r.json();
      const sorted = data.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setIncidents(sorted);
      for (const inc of sorted) {
        if (inc.status === "resolved" && !seenResolved.current.has(inc.incident_id)) {
          seenResolved.current.add(inc.incident_id);
          setDoneInc(inc);
        }
      }
    } catch {}
  }, []);

  useEffect(() => {
    if (page !== "dashboard") return;
    const sid = session?.session_id;
    fetchIncidents(sid);
    const id = setInterval(() => fetchIncidents(sid), 2500);
    return () => clearInterval(id);
  }, [page, session, fetchIncidents]);

  const handleConnected = (data) => {
    setSession(data); navigate("dashboard");
  };

  const handleDisconnect = () => {
    localStorage.removeItem("spark_session");
    setSession(null); setIncidents([]); seenResolved.current.clear();
    navigate("home");
  };

  const simulate = async () => {
    if (!session || simulating) return;
    setSimulating(true);
    try {
      const r = await fetch(`${API}/sessions/${session.session_id}/simulate`, { method:"POST" });
      if (r.status === 404) {
        // Session expired — recreate demo session and retry
        const nr = await fetch(`${API}/demo`, { method:"POST" });
        if (!nr.ok) return;
        const newSession = await nr.json();
        localStorage.setItem("spark_session", JSON.stringify(newSession));
        setSession(newSession);
        await fetch(`${API}/sessions/${newSession.session_id}/simulate`, { method:"POST" });
      }
    } finally { setSimulating(false); }
  };

  // Count active incidents for the siren badge
  const activeIncidentCount = incidents.filter(
    i => i.decision == null && i.status !== "rejected" && i.status !== "resolved"
  ).length;

  return (
    <>
      <Navbar
        t={t} dark={dark} toggleDark={() => setDark(d => !d)}
        onHome={() => navigate("home")}
        onConnect={() => navigate("connect")}
        session={session}
        onDisconnect={handleDisconnect}
        activeIncidents={activeIncidentCount}
      />

      {page === "home" && (
        <HomePage t={t} onConnect={() => navigate("connect")} onDemo={startDemo} />
      )}

      {page === "connect" && (
        <ConnectPage t={t} onBack={() => navigate("home")} onConnected={handleConnected} />
      )}

      {page === "dashboard" && (
        <DashboardPage
          t={t} session={session}
          incidents={incidents}
          onSimulate={simulate} simulating={simulating}
          doneInc={doneInc} onCloseDone={() => setDoneInc(null)}
        />
      )}

      <style>{CSS}</style>
    </>
  );
}

const CSS = `
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  textarea:focus, input:focus { border-color: #f97316 !important; }
  details summary::-webkit-details-marker { color: currentColor; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.35; }
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes popIn {
    0%   { transform: scale(0.5); opacity: 0; }
    100% { transform: scale(1);   opacity: 1; }
  }
  @keyframes heroFlame {
    0%   { transform: scale(1)    rotate(-2deg); filter: drop-shadow(0 0 8px rgba(249,115,22,0.6)); }
    100% { transform: scale(1.06) rotate(2deg);  filter: drop-shadow(0 0 20px rgba(249,115,22,0.9)) brightness(1.1); }
  }
  @keyframes fireFlicker {
    0%   { filter: drop-shadow(0 0 6px #f97316) brightness(1.0); transform: scale(1) rotate(-1deg); }
    33%  { filter: drop-shadow(0 0 18px #fbbf24) drop-shadow(0 0 8px #ef4444) brightness(1.12); transform: scale(1.03) rotate(0.5deg); }
    66%  { filter: drop-shadow(0 0 24px #f97316) drop-shadow(0 0 12px #dc2626) brightness(1.08); transform: scale(1.01) rotate(-0.5deg); }
    100% { filter: drop-shadow(0 0 10px #ea580c) brightness(1.05); transform: scale(1.04) rotate(1deg); }
  }
  @keyframes fireGlow {
    0%   { opacity: 0.4; transform: scale(0.95); }
    100% { opacity: 1.0; transform: scale(1.05); }
  }
  @keyframes sirenPing {
    0%        { transform: scale(1);   opacity: 0.85; }
    70%, 100% { transform: scale(3.2); opacity: 0; }
  }
  @keyframes waitDot {
    0%, 60%, 100% { transform: translateY(0);    opacity: 0.4; }
    30%            { transform: translateY(-4px); opacity: 1; }
  }
`;
