
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { formatApiError } from "../api/client";
import "./Auth.css";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    email: "",
    password: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  function handleChange(e) {
    setForm({
      ...form,
      [e.target.name]: e.target.value,
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const user = await login(form);
      const role = user?.role?.toUpperCase();

      if (role === "OWNER") {
        navigate("/owner/dashboard", { replace: true });
      } else if (role === "ADMIN") {
        navigate("/admin/dashboard", { replace: true });
      } else if (role === "STUDENT") {
        navigate("/student/dashboard", { replace: true });
      } else {
        setError("Your account has an invalid role. Please contact the administrator.");
      }
    } catch (err) {
      setError(formatApiError(err, "Login failed. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-orb auth-orb-one" />
      <div className="auth-orb auth-orb-two" />
      <div className="auth-orb auth-orb-three" />

      <div className="auth-decoration auth-decoration-one" />
      <div className="auth-decoration auth-decoration-two" />

      <section className="auth-card">
        <Link to="/" className="brand">
          <span className="brand-mark">O</span>
          OpenBench<span className="brand-dot">.</span>
        </Link>

        <div className="auth-welcome">
          <span className="auth-eyebrow">WELCOME BACK</span>
          <h1>Good to see you <span>again.</span></h1>
          <p className="auth-subtitle">
            Sign in to discover, book, and share campus resources.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="login-email">Email address</label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">✉</span>
              <input
                id="login-email"
                type="email"
                name="email"
                placeholder="you@example.com"
                value={form.email}
                onChange={handleChange}
                autoComplete="email"
                required
              />
            </div>
          </div>

          <div className="auth-field">
            <div className="auth-label-row">
              <label htmlFor="login-password">Password</label>
            </div>

            <div className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">⌑</span>
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Enter your password"
                value={form.password}
                onChange={handleChange}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="auth-password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="auth-submit"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="auth-spinner" />
                Signing in...
              </>
            ) : (
              <>
                Sign in
                <span aria-hidden="true">→</span>
              </>
            )}
          </button>
        </form>

        <div className="auth-divider">
          <span>YOUR CAMPUS, CONNECTED</span>
        </div>

        <p className="auth-footer">
          Don't have an account?{" "}
          <Link to="/register">Create an account <span>→</span></Link>
        </p>

        <p className="auth-bottom-note">
          Secure access to your campus resources.
        </p>
      </section>
    </main>
  );
}
