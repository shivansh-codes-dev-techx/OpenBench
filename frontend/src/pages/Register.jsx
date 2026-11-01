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

        <form onSubmit={handleSubmit}>
          <label>Full name</label>
          <input
            name="full_name"
            placeholder="Your full name"
            value={form.full_name}
            onChange={handleChange}
            required
          />

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
            placeholder="Create a password"
            value={form.password}
            onChange={handleChange}
            minLength={8}
            required
          />

          <label>Institution</label>
          <input
            name="institution"
            placeholder="Your college or university"
            value={form.institution}
            onChange={handleChange}
          />

          <label>Account type</label>
          <select name="role" value={form.role} onChange={handleChange}>
            <option value="STUDENT">Student</option>
            <option value="OWNER">Resource Owner</option>
          </select>

          {error && <p className="auth-error">{error}</p>}

          <button type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="auth-footer">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
