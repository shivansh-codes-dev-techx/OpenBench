
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CalendarDays, CheckCircle } from "lucide-react";

import { apiRequest } from "../api/client";
import "./Booking.css";

function getLocalDateTime() {
    const date = new Date();
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
}

export default function Booking() {
    const { id } = useParams();
    const navigate = useNavigate();

    const [resource, setResource] = useState(null);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");
    const [confirmed, setConfirmed] = useState(false);
    const [bookingData, setBookingData] = useState(null);

    const [form, setForm] = useState({
        start_at: "",
        end_at: "",
        purpose: "",
    });

    const minDateTime = getLocalDateTime();

    // Fetch actual resource from backend
    useEffect(() => {
        async function fetchResource() {
            try {
                setLoading(true);
                setError("");

                const response = await apiRequest(`/resources/${id}`);

                setResource(response.data ?? response);
            } catch (err) {
                setError(
                    typeof err.message === "string"
                        ? err.message
                        : "Unable to load resource."
                );
            } finally {
                setLoading(false);
            }
        }

        fetchResource();
    }, [id]);

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");

        if (!form.start_at || !form.end_at || !form.purpose.trim()) {
            setError("Please complete all booking fields.");
            return;
        }

        if (new Date(form.start_at) <= new Date()) {
            setError("Start time must be in the future.");
            return;
        }

        if (new Date(form.end_at) <= new Date(form.start_at)) {
            setError("End time must be later than start time.");
            return;
        }

        if (form.purpose.trim().length < 5) {
            setError("Purpose must contain at least 5 characters.");
            return;
        }

        try {
            setSubmitting(true);

            const payload = {
                resource_id: Number(id),
                start_at: new Date(form.start_at).toISOString(),
                end_at: new Date(form.end_at).toISOString(),
                purpose: form.purpose.trim(),
            };

            const response = await apiRequest("/bookings", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            setBookingData(response.data ?? response);
            setConfirmed(true);
        } catch (err) {
            const message = Array.isArray(err.message)
                ? err.message.map((item) => item.msg || item.message).join(", ")
                : err.message;

            setError(message || "Booking request failed. Please try again.");
        } finally {
            setSubmitting(false);
        }
    }

    if (loading) {
        return (
            <main className="booking-page">
                <section className="booking-card">
                    <p>Loading resource details...</p>
                </section>
            </main>
        );
    }

    if (!resource || !resource.is_active) {
        return (
            <main className="booking-page">
                <section className="booking-card">
                    <h1>Resource unavailable</h1>
                    <p>{error || "This resource is not currently available."}</p>
                    <Link to="/student/dashboard">Return to dashboard</Link>
                </section>
            </main>
        );
    }

    if (confirmed) {
        return (
            <main className="booking-page">
                <section className="booking-card success-card">
                    <CheckCircle size={55} color="#4ade80" />

                    <h1>Booking Request Submitted!</h1>

                    <p>
                        Your booking request for{" "}
                        <strong>{resource.title}</strong> has been submitted
                        successfully.
                    </p>

                    <p>
                        Your request is now awaiting the resource owner's
                        decision.
                    </p>

                    {bookingData?.id && (
                        <p>
                            Booking ID: <strong>{bookingData.id}</strong>
                        </p>
                    )}

                    <button onClick={() => navigate("/student/dashboard")}>
                        Back to Dashboard
                    </button>
                </section>
            </main>
        );
    }

    return (
        <main className="booking-page">
            <Link
                to={`/resources/${resource.id}`}
                className="booking-back"
            >
                <ArrowLeft size={18} />
                Back to resource
            </Link>

            <section className="booking-card">
                <div className="booking-heading-icon">
                    <CalendarDays size={30} />
                </div>

                <p className="booking-eyebrow">CAMPUS RESOURCE BOOKING</p>
                <h1>Request a Booking</h1>

                <p className="booking-resource-name">
                    Resource: <strong>{resource.title}</strong>
                </p>

                <p>{resource.location}</p>

                <form onSubmit={handleSubmit}>
                    <label>Start date and time</label>
                    <input
                        type="datetime-local"
                        required
                        min={minDateTime}
                        value={form.start_at}
                        onChange={(e) =>
                            setForm({ ...form, start_at: e.target.value })
                        }
                    />

                    <label>End date and time</label>
                    <input
                        type="datetime-local"
                        required
                        min={form.start_at || minDateTime}
                        value={form.end_at}
                        onChange={(e) =>
                            setForm({ ...form, end_at: e.target.value })
                        }
                    />

                    <label>Purpose of booking</label>
                    <textarea
                        required
                        minLength={5}
                        maxLength={2000}
                        rows="4"
                        placeholder="Explain why you need this resource..."
                        value={form.purpose}
                        onChange={(e) =>
                            setForm({ ...form, purpose: e.target.value })
                        }
                    />

                    {error && (
                        <p className="booking-error">{error}</p>
                    )}

                    <button type="submit" disabled={submitting}>
                        {submitting ? "Submitting..." : "Submit Booking Request"}
                    </button>
                </form>
            </section>
        </main>
    );
}
