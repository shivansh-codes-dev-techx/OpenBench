
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
      <section className="auth-card">
        <Link to="/" className="brand">
          OpenBench.
        </Link>

        <h1>Welcome back</h1>

        <p className="auth-subtitle">
          Sign in to discover and share campus resources.
        </p>

        <form onSubmit={handleSubmit}>
          <label>Email address</label>

          <input
            type="email"
            name="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={handleChange}
            required
          />

          <label>Password</label>

          <input
            type="password"
            name="password"
            placeholder="Enter your password"
            value={form.password}
            onChange={handleChange}
            required
          />

          {error && (
            <p className="auth-error">
              {error}
            </p>
          )}

          <button type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="auth-footer">
          Don't have an account?{" "}
          <Link to="/register">Create one</Link>
        </p>
      </section>
    </main>
  );
}
