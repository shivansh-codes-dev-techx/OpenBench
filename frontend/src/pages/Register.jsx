
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
    role: "STUDENT",
    institution: "",
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
      const user = await register(form);
      const role = user?.role?.toUpperCase();

      if (role === "OWNER") {
        navigate("/owner/dashboard");
      } else {
        navigate("/student/dashboard");
      }
    } catch (err) {
      setError(
        formatApiError(err, "Registration failed. Please try again.")
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page register-page">
      <div className="auth-orb auth-orb-one" />
      <div className="auth-orb auth-orb-two" />
      <div className="auth-orb auth-orb-three" />

      <div className="auth-decoration auth-decoration-one" />
      <div className="auth-decoration auth-decoration-two" />

      <section className="auth-card register-card">
        <Link to="/" className="brand">
          <span className="brand-mark">O</span>
          OpenBench<span className="brand-dot">.</span>
        </Link>

        <div className="auth-welcome">
          <span className="auth-eyebrow">JOIN THE COMMUNITY</span>

          <h1>
            Create your <span>account.</span>
          </h1>

          <p className="auth-subtitle">
            Join your campus resource-sharing community.
            Discover more. Share more. Do more.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="register-name">Full name</label>

            <div className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">
                ♙
              </span>

              <input
                id="register-name"
                type="text"
                name="full_name"
                placeholder="Enter your full name"
                value={form.full_name}
                onChange={handleChange}
                autoComplete="name"
                required
              />
            </div>
          </div>

          <div className="auth-field">
            <label htmlFor="register-email">Email address</label>

            <div className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">
                ✉
              </span>

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

            <div className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">
                ⌑
              </span>

              <input
                id="register-password"
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Create a password"
                value={form.password}
                onChange={handleChange}
                autoComplete="new-password"
                minLength={8}
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

            <span className="register-hint">
              Use at least 8 characters.
            </span>
          </div>

          <div className="auth-field">
            <label htmlFor="register-institution">
              Institution <span className="optional-label">(Optional)</span>
            </label>

            <div className="auth-input-wrap">
              <span className="auth-input-icon" aria-hidden="true">
                ⌂
              </span>

              <input
                id="register-institution"
                type="text"
                name="institution"
                placeholder="Your college or university"
                value={form.institution}
                onChange={handleChange}
                autoComplete="organization"
              />
            </div>
          </div>

          <div className="auth-field">
            <label>Choose your account type</label>

            <div className="role-selection">
              <button
                type="button"
                className={`role-card ${form.role === "STUDENT" ? "role-card-active" : ""
                  }`}
                onClick={() =>
                  setForm({ ...form, role: "STUDENT" })
                }
                aria-pressed={form.role === "STUDENT"}
              >
                <span className="role-check">
                  {form.role === "STUDENT" ? "✓" : ""}
                </span>

                <span className="role-icon">🎓</span>
                <span className="role-title">Student</span>

                <span className="role-description">
                  Discover and book campus resources.
                </span>
              </button>

              <button
                type="button"
                className={`role-card ${form.role === "OWNER" ? "role-card-active" : ""
                  }`}
                onClick={() =>
                  setForm({ ...form, role: "OWNER" })
                }
                aria-pressed={form.role === "OWNER"}
              >
                <span className="role-check">
                  {form.role === "OWNER" ? "✓" : ""}
                </span>

                <span className="role-icon">🏅</span>
                <span className="role-title">Resource Owner</span>

                <span className="role-description">
                  Manage and share campus resources.
                </span>
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

        <div className="auth-divider">
          <span>ALREADY PART OF OPENBENCH?</span>
        </div>

        <p className="auth-footer">
          Already registered?{" "}
          <Link to="/login">
            Sign in <span>→</span>
          </Link>
        </p>

        <p className="auth-bottom-note">
          Your campus community starts here.
        </p>
      </section>
    </main>
  );
}
