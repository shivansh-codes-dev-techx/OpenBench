
import { useEffect, useState } from "react";
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

    if (type === "SPACE") return Armchair;

    if (title.includes("camera") || category.includes("photography")) {
        return Camera;
    }

    if (title.includes("projector") || title.includes("monitor")) {
        return Monitor;
    }

    return Laptop;
}

export default function ResourceDetails() {
    const { id } = useParams();

    const [resource, setResource] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    async function fetchResource() {
        try {
            setLoading(true);
            setError("");

            const response = await fetch(
                `${API_BASE_URL}/resources/${id}`
            );

            if (response.status === 404) {
                setResource(null);
                setError("This resource could not be found or is no longer available.");
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
            console.error("Resource details error:", err);
            setError(
                err.message || "Unable to connect to the server."
            );
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        fetchResource();
    }, [id]);

    // Loading state
    if (loading) {
        return (
            <main className="details-page">
                <p className="empty-state">
                    Loading resource details...
                </p>
            </main>
        );
    }

    // Error or resource not found
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
                        onClick={fetchResource}
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

    const ResourceIcon = getResourceIcon(resource);

    const formatDate = (date) => {
        if (!date) return "Not specified";

        const parsedDate = new Date(date);

        if (Number.isNaN(parsedDate.getTime())) {
            return "Not specified";
        }

        return parsedDate.toLocaleString();
    };

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
                    <ResourceIcon size={42} />
                </div>

                <span className="details-category">
                    {resource.category}
                </span>

                <h1>{resource.title}</h1>

                <p className="details-description">
                    {resource.description ||
                        `Explore the ${resource.title} available at ${resource.location}.`}
                </p>

                {/* RESOURCE INFORMATION */}
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
                        <span>Resource Owner ID: {resource.owner_id}</span>
                    </div>

                </div>

                {/* USAGE RULES */}
                <div className="details-rules">
                    <h3>Usage Rules</h3>

                    <p>
                        {resource.usage_rules ||
                            "No specific usage rules have been provided. Please contact the resource owner before use."}
                    </p>
                </div>

                {/* AVAILABILITY */}
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

                {/* BOOKING BUTTON */}
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
