import { useState } from "react";

import { useAuth } from "../auth/AuthProvider";

export function LoginForm() {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setBusy(true);
    const { error: err } = mode === "signin" ? await signIn(email, password) : await signUp(email, password);
    setBusy(false);
    if (err) {
      setError(err);
    } else if (mode === "signup") {
      setMessage("Check your email to confirm your account, then sign in.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-sm flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-950 p-6"
      >
        <h1 className="text-lg font-semibold text-neutral-100">
          Mission Control <span className="text-neutral-600">— Refactor Agent</span>
        </h1>
        <p className="text-xs text-neutral-500">{mode === "signin" ? "Sign in to continue" : "Create an account"}</p>

        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm text-neutral-100"
        />
        <input
          type="password"
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm text-neutral-100"
        />

        {error && <p className="text-sm text-rose-400">{error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        <button
          type="submit"
          disabled={busy}
          className="rounded bg-sky-500 px-4 py-1.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Working…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setError(null);
            setMessage(null);
          }}
          className="text-xs text-neutral-500 hover:text-neutral-300"
        >
          {mode === "signin" ? "Need an account? Sign up" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
