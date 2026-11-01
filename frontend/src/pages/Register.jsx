import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { formatApiError } from "../api/client";
import "./Auth.css";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    institution: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const user = await register(form);

      const role = user?.role?.toUpperCase();

      if (role === "OWNER") {
        navigate("/owner/dashboard");
      } else {
        navigate("/student/dashboard");
      }
    } catch (err) {
      setError(formatApiError(err, "Registration failed. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <Link to="/" className="brand">OpenBench.</Link>

        <h1>Create your account</h1>
        <p className="auth-subtitle">
          Join your campus resource-sharing community.
        </p>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="register-full-name">Full name</label>
            <div className="auth-input-wrap auth-input-wrap--plain">
              <input
                id="register-full-name"
                name="full_name"
                placeholder="Your full name"
                value={form.full_name}
                onChange={handleChange}
                autoComplete="name"
                required
              />
            </div>
          </div>

          <div className="auth-field">
            <label htmlFor="register-email">Email address</label>
            <div className="auth-input-wrap auth-input-wrap--plain">
              <input
                id="register-email"
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
            <label htmlFor="register-password">Password</label>
            <div className="auth-input-wrap auth-input-wrap--plain">
              <input
                id="register-password"
                type="password"
                name="password"
                placeholder="Create a password"
                value={form.password}
                onChange={handleChange}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>
          </div>

          <div className="auth-field">
            <label htmlFor="register-institution">Institution</label>
            <div className="auth-input-wrap auth-input-wrap--plain">
              <input
                id="register-institution"
                name="institution"
                placeholder="Your college or university"
                value={form.institution}
                onChange={handleChange}
                autoComplete="organization"
              />
            </div>
          </div>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? (
              <>
                <span className="auth-spinner" />
                Creating account...
              </>
            ) : (
              <>
                Create account
                <span aria-hidden="true">→</span>
              </>
            )}
          </button>
        </form>

        <p className="auth-footer">
          Resource owners are added by an OpenBench administrator. If you have
          an owner account, sign in instead.
        </p>

        <p className="auth-footer">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
