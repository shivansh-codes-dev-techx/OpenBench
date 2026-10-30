
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
    ArrowLeft,
    MapPin,
    Package,
    ShieldCheck,
    CalendarDays,
    Laptop,
    Monitor,
    Camera,
    Armchair,
    RefreshCw,
} from "lucide-react";

import "./ResourceDetails.css";

const API_BASE_URL = (
    import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

function getResourceIcon(resource) {
    const type = resource?.resource_type?.toUpperCase();
    const category = resource?.category?.toLowerCase() || "";
    const title = resource?.title?.toLowerCase() || "";

    if (type === "SPACE") return <Armchair size={42} />;

    if (title.includes("camera") || category.includes("photography")) {
        return <Camera size={42} />;
    }

    if (title.includes("projector") || title.includes("monitor")) {
        return <Monitor size={42} />;
    }

    return <Laptop size={42} />;
}

function formatDate(date) {
    if (!date) return "Not specified";

    const parsedDate = new Date(date);

    if (Number.isNaN(parsedDate.getTime())) {
        return "Not specified";
    }

    return parsedDate.toLocaleString();
}

export default function ResourceDetails() {
    const { id } = useParams();

    const [resource, setResource] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [retryCount, setRetryCount] = useState(0);

    const fetchResource = useCallback(async (signal) => {
        try {
            setError("");

            const response = await fetch(
                `${API_BASE_URL}/resources/${id}`,
                { signal }
            );

            if (response.status === 404) {
                setResource(null);
                setError(
                    "This resource could not be found or is no longer available."
                );
                return;
            }

            if (!response.ok) {
                throw new Error(
                    `Unable to load resource (${response.status}).`
                );
            }

            const data = await response.json();
            setResource(data);
        } catch (err) {
            if (err.name === "AbortError") return;

            console.error("Resource details error:", err);

            setError(
                err.message || "Unable to connect to the server."
            );
        }
    }, [id]);

    useEffect(() => {
        const controller = new AbortController();

        async function loadResource() {
            setLoading(true);

            try {
                await fetchResource(controller.signal);
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            }
        }

        loadResource();

        return () => {
            controller.abort();
        };
    }, [fetchResource, retryCount]);

    function handleRetry() {
        setLoading(true);
        setRetryCount((previous) => previous + 1);
    }

    if (loading) {
        return (
            <main className="details-page">
                <p className="empty-state">
                    Loading resource details...
                </p>
            </main>
        );
    }

    if (error || !resource) {
        return (
            <main className="details-page">
                <h1>
                    {error.includes("could not be found")
                        ? "Resource not found"
                        : "Unable to load resource"}
                </h1>

                <p>{error || "This resource is unavailable."}</p>

                {error && !error.includes("could not be found") && (
                    <button
                        className="book-resource-button"
                        onClick={handleRetry}
                    >
                        <RefreshCw size={18} />
                        Try Again
                    </button>
                )}

                <Link
                    to="/student/dashboard"
                    className="back-link"
                >
                    <ArrowLeft size={18} />
                    Back to dashboard
                </Link>
            </main>
        );
    }

    return (
        <main className="details-page">
            <Link
                to="/student/dashboard"
                className="back-link"
            >
                <ArrowLeft size={18} />
                Back to resources
            </Link>

            <section className="details-card">
                <div className="details-icon">
                    {getResourceIcon(resource)}
                </div>

                <span className="details-category">
                    {resource.category}
                </span>

                <h1>{resource.title}</h1>

                <p className="details-description">
                    {resource.description ||
                        `Explore the ${resource.title} available at ${resource.location}.`}
                </p>

                <div className="details-info">
                    <div>
                        <MapPin size={19} />
                        <span>{resource.location}</span>
                    </div>

                    <div>
                        <Package size={19} />
                        <span>{resource.resource_type}</span>
                    </div>

                    <div>
                        <ShieldCheck size={19} />
                        <span>
                            Resource Owner ID: {resource.owner_id}
                        </span>
                    </div>
                </div>

                <div className="details-rules">
                    <h3>Usage Rules</h3>

                    <p>
                        {resource.usage_rules ||
                            "No specific usage rules have been provided. Please contact the resource owner before use."}
                    </p>
                </div>

                <div className="details-rules">
                    <h3>Availability Information</h3>

                    <p>
                        Available from: {formatDate(resource.available_from)}
                    </p>

                    <p>
                        Available until: {formatDate(resource.available_until)}
                    </p>
                </div>

                <div className="details-availability">
                    <span className="details-available">
                        Available
                    </span>
                </div>

                {resource.is_active && (
                    <Link
                        to={`/book/${resource.id}`}
                        className="book-resource-button"
                    >
                        <CalendarDays size={18} />
                        Request Booking
                    </Link>
                )}
            </section>
        </main>
    );
}
