import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle, RefreshCw, Upload, XCircle } from "lucide-react";

import { apiRequest, formatApiError } from "../api/client";
import OwnerPortalNav from "./OwnerPortalNav";
import "./OwnerDashboard.css";
import "./OwnerResources.css";

const REQUIRED_ANGLES = ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"];
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

function formatAvailability(value) {
    if (!value) return "Not specified";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
        ? "Not specified"
        : parsed.toLocaleString();
}

function formatDateTimeInput(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60_000)
        .toISOString()
        .slice(0, 16);
}

function baselineKey(resourceId, angle) {
    return `${resourceId}:${angle}`;
}

export default function OwnerResources() {
    const [searchParams] = useSearchParams();
    const [resources, setResources] = useState([]);
    const [baselineData, setBaselineData] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");
    const [editingId, setEditingId] = useState(null);
    const [editValues, setEditValues] = useState({});
    const [editInitialAvailability, setEditInitialAvailability] = useState({});
    const [savingId, setSavingId] = useState(null);
    const [uploading, setUploading] = useState({});
    const [uploadErrors, setUploadErrors] = useState({});
    const [refreshing, setRefreshing] = useState({});
    const inFlightUploads = useRef(new Set());

    const loadResources = useCallback(async () => {
        try {
            const result = await apiRequest("/resources/owner");
            if (!Array.isArray(result)) {
                throw new Error("Unexpected resources response from server.");
            }
            setResources(result);
            setBaselineData(
                Object.fromEntries(
                    result.map((resource) => [resource.id, { loading: true }])
                )
            );

            const baselines = await Promise.all(
                result.map(async (resource) => {
                    try {
                        const data = await apiRequest(
                            `/resources/${resource.id}/baseline-images`
                        );
                        return [resource.id, data];
                    } catch (requestError) {
                        return [
                            resource.id,
                            {
                                error: formatApiError(requestError),
                                loading: false,
                            },
                        ];
                    }
                })
            );
            setBaselineData(Object.fromEntries(baselines));
        } catch (requestError) {
            setError(
                formatApiError(requestError, "Unable to load your resources.")
            );
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void Promise.resolve().then(loadResources);
    }, [loadResources]);

    const requestedResourceId = Number(searchParams.get("resource"));

    useEffect(() => {
        if (!requestedResourceId || loading) return;
        document.getElementById(`owner-resource-${requestedResourceId}`)?.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }, [loading, requestedResourceId]);

    async function refreshBaselines(resourceId) {
        setRefreshing((current) => ({ ...current, [resourceId]: true }));
        setBaselineData((current) => ({
            ...current,
            [resourceId]: {
                ...current[resourceId],
                loading: true,
                error: "",
            },
        }));
        try {
            const data = await apiRequest(
                `/resources/${resourceId}/baseline-images`
            );
            setBaselineData((current) => ({
                ...current,
                [resourceId]: { ...data, loading: false },
            }));
        } catch (requestError) {
            setBaselineData((current) => ({
                ...current,
                [resourceId]: {
                    ...current[resourceId],
                    loading: false,
                    error: formatApiError(requestError),
                },
            }));
        } finally {
            setRefreshing((current) => ({
                ...current,
                [resourceId]: false,
            }));
        }
    }

    function beginEdit(resource) {
        setSuccess("");
        setEditingId(resource.id);
        setEditValues({
            title: resource.title || "",
            description: resource.description || "",
            category: resource.category || "",
            location: resource.location || "",
            usage_rules: resource.usage_rules || "",
            is_active: Boolean(resource.is_active),
            available_from: formatDateTimeInput(resource.available_from),
            available_until: formatDateTimeInput(resource.available_until),
        });
        setEditInitialAvailability({
            available_from: formatDateTimeInput(resource.available_from),
            available_until: formatDateTimeInput(resource.available_until),
        });
    }

    async function saveEdit(event, resourceId) {
        event.preventDefault();
        setSavingId(resourceId);
        setError("");
        setSuccess("");
        try {
            const payload = {
                ...editValues,
                title: editValues.title.trim(),
                category: editValues.category.trim(),
                location: editValues.location.trim(),
            };
            for (const field of ["available_from", "available_until"]) {
                if (editValues[field] !== editInitialAvailability[field]) {
                    payload[field] = editValues[field]
                        ? new Date(editValues[field]).toISOString()
                        : null;
                } else {
                    delete payload[field];
                }
            }
            const updated = await apiRequest(`/resources/${resourceId}`, {
                method: "PATCH",
                body: JSON.stringify(payload),
            });
            setResources((current) =>
                current.map((resource) =>
                    resource.id === resourceId ? updated : resource
                )
            );
            setEditingId(null);
            setSuccess("Resource updated successfully.");
        } catch (requestError) {
            setError(
                formatApiError(requestError, "Unable to update this resource.")
            );
        } finally {
            setSavingId(null);
        }
    }

    async function uploadBaseline(event, resourceId, angle, baselineExists) {
        const input = event.currentTarget;
        const file = input.files?.[0];
        if (!file) return;

        const key = baselineKey(resourceId, angle);
        if (inFlightUploads.current.has(key)) {
            input.value = "";
            return;
        }
        inFlightUploads.current.add(key);
        setUploading((current) => ({ ...current, [key]: true }));
        setUploadErrors((current) => ({ ...current, [key]: "" }));
        setSuccess("");

        try {
            if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
                throw new Error("Choose a JPEG, PNG, or WEBP image.");
            }
            if (file.size > MAX_IMAGE_BYTES) {
                throw new Error("Image must not exceed 15 MiB.");
            }

            const body = new FormData();
            body.append("file", file);
            if (!baselineExists) body.append("angle", angle);

            await apiRequest(
                baselineExists
                    ? `/resources/${resourceId}/baseline-images/${angle}`
                    : `/resources/${resourceId}/baseline-images`,
                {
                    method: baselineExists ? "PUT" : "POST",
                    body,
                }
            );
            setSuccess(`${angle} baseline uploaded for this resource.`);
            await refreshBaselines(resourceId);
        } catch (requestError) {
            setUploadErrors((current) => ({
                ...current,
                [key]: formatApiError(
                    requestError,
                    "Unable to upload this baseline image."
                ),
            }));
        } finally {
            inFlightUploads.current.delete(key);
            setUploading((current) => ({ ...current, [key]: false }));
            input.value = "";
        }
    }

    const hasUploadsInFlight = Object.values(uploading).some(Boolean);

    return (
        <div className="owner-dashboard">
            <OwnerPortalNav />
            <main className="owner-main owner-resources-main">
                <header className="owner-header owner-resources-header">
                    <div>
                        <p className="owner-eyebrow">RESOURCE MANAGEMENT</p>
                        <h1>My Resources</h1>
                        <p className="owner-muted">
                            Edit your listings and keep all six inspection baselines valid.
                        </p>
                    </div>
                    <button
                        type="button"
                        className="resource-action"
                        onClick={() => {
                            setLoading(true);
                            setError("");
                            void loadResources();
                        }}
                        disabled={loading || hasUploadsInFlight}
                    >
                        <RefreshCw size={16} />
                        Refresh
                    </button>
                </header>

                {success && (
                    <p className="owner-success-message" role="status">{success}</p>
                )}
                {error && (
                    <p className="owner-error-message" role="alert">{error}</p>
                )}

                {loading && <p className="owner-muted">Loading your resources...</p>}
                {!loading && !error && resources.length === 0 && (
                    <p className="owner-muted">
                        You have not published any resources yet.
                    </p>
                )}

                <div className="owner-managed-resource-list">
                    {resources.map((resource) => {
                        const baseline = baselineData[resource.id] || {};
                        const images = baseline.images || [];
                        const imageByAngle = new Map(
                            images.map((image) => [image.angle, image])
                        );
                        const missing = new Set(
                            baseline.missing_angles || REQUIRED_ANGLES
                        );
                        const invalid = baseline.invalid_angles || {};
                        const isEditing = editingId === resource.id;

                        return (
                            <article
                                className="owner-managed-resource"
                                id={`owner-resource-${resource.id}`}
                                key={resource.id}
                            >
                                <div className="owner-managed-resource-heading">
                                    <div>
                                        <span className="owner-resource-category">
                                            {resource.category}
                                        </span>
                                        <h2>{resource.title}</h2>
                                        <p className="owner-muted">
                                            {resource.description || "No description provided."}
                                        </p>
                                    </div>
                                    <span className={`owner-status ${resource.is_active ? "available-status" : "unavailable-status"}`}>
                                        {resource.is_active ? "Active" : "Inactive"}
                                    </span>
                                </div>

                                <dl className="owner-resource-details">
                                    <div><dt>Location</dt><dd>{resource.location}</dd></div>
                                    <div><dt>Type</dt><dd>{resource.resource_type}</dd></div>
                                    <div><dt>Available from</dt><dd>{formatAvailability(resource.available_from)}</dd></div>
                                    <div><dt>Available until</dt><dd>{formatAvailability(resource.available_until)}</dd></div>
                                    <div className="owner-resource-rules"><dt>Usage rules</dt><dd>{resource.usage_rules || "None specified."}</dd></div>
                                </dl>

                                {isEditing ? (
                                    <form
                                        className="owner-resource-edit-form"
                                        onSubmit={(event) => void saveEdit(event, resource.id)}
                                    >
                                        <label>
                                            Name
                                            <input
                                                required
                                                minLength={2}
                                                maxLength={150}
                                                value={editValues.title}
                                                onChange={(event) => setEditValues((current) => ({ ...current, title: event.target.value }))}
                                            />
                                        </label>
                                        <label>
                                            Description
                                            <textarea
                                                value={editValues.description}
                                                onChange={(event) => setEditValues((current) => ({ ...current, description: event.target.value }))}
                                            />
                                        </label>
                                        <label>
                                            Category
                                            <input
                                                required
                                                minLength={2}
                                                maxLength={100}
                                                value={editValues.category}
                                                onChange={(event) => setEditValues((current) => ({ ...current, category: event.target.value }))}
                                            />
                                        </label>
                                        <label>
                                            Location
                                            <input
                                                required
                                                minLength={2}
                                                maxLength={200}
                                                value={editValues.location}
                                                onChange={(event) => setEditValues((current) => ({ ...current, location: event.target.value }))}
                                            />
                                        </label>
                                        <label>
                                            Usage rules
                                            <textarea
                                                value={editValues.usage_rules}
                                                onChange={(event) => setEditValues((current) => ({ ...current, usage_rules: event.target.value }))}
                                            />
                                        </label>
                                        <label>
                                            Available from
                                            <input
                                                type="datetime-local"
                                                value={editValues.available_from}
                                                onChange={(event) => setEditValues((current) => ({ ...current, available_from: event.target.value }))}
                                            />
                                        </label>
                                        <label>
                                            Available until
                                            <input
                                                type="datetime-local"
                                                value={editValues.available_until}
                                                onChange={(event) => setEditValues((current) => ({ ...current, available_until: event.target.value }))}
                                            />
                                        </label>
                                        <label className="owner-active-toggle">
                                            <input
                                                type="checkbox"
                                                checked={editValues.is_active}
                                                onChange={(event) => setEditValues((current) => ({ ...current, is_active: event.target.checked }))}
                                            />
                                            Listed as active
                                        </label>
                                        <div className="owner-resource-form-actions">
                                            <button type="submit" disabled={savingId === resource.id}>
                                                {savingId === resource.id ? "Saving..." : "Save changes"}
                                            </button>
                                            <button type="button" className="cancel-button" onClick={() => setEditingId(null)}>
                                                Cancel
                                            </button>
                                        </div>
                                    </form>
                                ) : (
                                    <button
                                        type="button"
                                        className="owner-resource-manage-button"
                                        onClick={() => beginEdit(resource)}
                                    >
                                        Edit resource
                                    </button>
                                )}

                                <section className="owner-baselines">
                                    <div className="owner-baselines-heading">
                                        <div>
                                            <h3>Inspection baselines</h3>
                                            <p className="owner-muted">
                                                {baseline.loading
                                                    ? "Checking baseline images..."
                                                    : baseline.error
                                                        ? baseline.error
                                                        : `${REQUIRED_ANGLES.length - missing.size - Object.keys(invalid).length} of 6 angles valid`}
                                            </p>
                                        </div>
                                        <button
                                            type="button"
                                            className="resource-action"
                                            onClick={() => void refreshBaselines(resource.id)}
                                            disabled={
                                                Boolean(refreshing[resource.id]) ||
                                                REQUIRED_ANGLES.some(
                                                    (angle) =>
                                                        uploading[baselineKey(resource.id, angle)]
                                                )
                                            }
                                        >
                                            <RefreshCw size={15} />
                                            {refreshing[resource.id] ? "Refreshing..." : "Refresh status"}
                                        </button>
                                    </div>

                                    {baseline.error && (
                                        <p className="owner-error-message" role="alert">{baseline.error}</p>
                                    )}
                                    <div className="owner-baseline-grid">
                                        {REQUIRED_ANGLES.map((angle) => {
                                            const image = imageByAngle.get(angle);
                                            const isInvalid = Boolean(invalid[angle]);
                                            const isValid = Boolean(image) && !missing.has(angle) && !isInvalid;
                                            const key = baselineKey(resource.id, angle);

                                            return (
                                                <div className={`owner-baseline-slot ${isValid ? "is-valid" : isInvalid ? "is-invalid" : "is-missing"}`} key={angle}>
                                                    <div className="owner-baseline-slot-status">
                                                        {isValid ? <CheckCircle size={17} /> : isInvalid ? <XCircle size={17} /> : <span aria-hidden="true">!</span>}
                                                        <strong>{angle}</strong>
                                                    </div>
                                                    <span className="owner-baseline-status-label">
                                                        {baseline.loading
                                                            ? "Checking..."
                                                            : isValid
                                                                ? "Valid"
                                                                : isInvalid
                                                                    ? "Invalid"
                                                                    : "Missing"}
                                                    </span>
                                                    {image && (
                                                        <p className="owner-baseline-filename" title={image.original_filename}>
                                                            {image.original_filename}
                                                        </p>
                                                    )}
                                                    {isInvalid && (
                                                        <p className="owner-baseline-error">{invalid[angle]}</p>
                                                    )}
                                                    <label className="owner-baseline-upload">
                                                        <Upload size={15} />
                                                        {uploading[key]
                                                            ? "Uploading..."
                                                            : image
                                                                ? "Replace image"
                                                                : "Upload image"}
                                                        <input
                                                            type="file"
                                                            accept="image/jpeg,image/png,image/webp"
                                                            aria-label={`${image ? "Replace" : "Upload"} ${angle} baseline image`}
                                                            disabled={Boolean(uploading[key]) || Boolean(baseline.error) || Boolean(baseline.loading)}
                                                            onChange={(event) => void uploadBaseline(event, resource.id, angle, Boolean(image))}
                                                        />
                                                    </label>
                                                    {uploadErrors[key] && (
                                                        <p className="owner-baseline-error" role="alert">{uploadErrors[key]}</p>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </section>
                            </article>
                        );
                    })}
                </div>
            </main>
        </div>
    );
}
