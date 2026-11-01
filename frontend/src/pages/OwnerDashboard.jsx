
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import InspectionComparison from "../components/inspection/InspectionComparison";

import {
    LayoutDashboard,
    Package,
    CalendarDays,
    Plus,
    Search,
    MapPin,
    CheckCircle,
    XCircle,
    Clock,
    LogOut,
    Laptop,
    Armchair,
    Monitor,
    Camera,
    RefreshCw,
} from "lucide-react";

import { useAuth } from "../context/useAuth";
import { apiRequest, formatApiError } from "../api/client";
import ResourceImage from "../components/ResourceImage";
import InspectionCapture from "../components/inspection/InspectionCapture";
import "./OwnerDashboard.css";

const RESOURCE_IMAGE_ANGLES = [
    "FRONT",
    "BACK",
    "LEFT",
    "RIGHT",
    "TOP",
    "BOTTOM",
];

function getResourceId(response) {
    const visited = new Set();

    function search(value, depth = 0) {
        if (!value || typeof value !== "object" || depth > 6) {
            return null;
        }

        if (visited.has(value)) return null;
        visited.add(value);

        if (Array.isArray(value)) {
            for (const item of value) {
                const result = search(item, depth + 1);
                if (result !== null) return result;
            }
            return null;
        }

        if (value.resource_id !== undefined && value.resource_id !== null) {
            return value.resource_id;
        }

        for (const key of ["resource", "data", "result"]) {
            if (value[key] && typeof value[key] === "object") {
                const result = search(value[key], depth + 1);
                if (result !== null) return result;
            }
        }

        if (value.id !== undefined && value.id !== null) {
            return value.id;
        }

        return null;
    }

    return search(response);
}

function getResourceIcon(resource) {
    const type = resource.resource_type?.toUpperCase();
    const title = resource.title?.toLowerCase() || "";
    const category = resource.category?.toLowerCase() || "";

    if (type === "SPACE") return Armchair;
    if (title.includes("projector") || title.includes("monitor")) return Monitor;
    if (title.includes("camera") || category.includes("photography")) return Camera;

    return Laptop;
}

function formatDate(value) {
    if (!value) return "Not available";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not available";

    return date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

function formatTime(value) {
    if (!value) return "Not available";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not available";

    return date.toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
    });
}

function getStatusLabel(status) {
    const value = status?.toUpperCase() || "UNKNOWN";
    return value.charAt(0) + value.slice(1).toLowerCase();
}

export default function OwnerDashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const [isNavOpen, setIsNavOpen] = useState(false);
    const [activeNav, setActiveNav] = useState("overview");
    const [highlightStyle, setHighlightStyle] = useState({
        top: 0,
        height: 56,
    });

    const navRef = useRef(null);

    const [resources, setResources] = useState([]);
    const [requests, setRequests] = useState([]);
    const [search, setSearch] = useState("");
    const [showForm, setShowForm] = useState(false);
    const [editingResourceId, setEditingResourceId] = useState(null);

    const [loadingResources, setLoadingResources] = useState(true);
    const [loadingRequests, setLoadingRequests] = useState(true);

    const [resourceError, setResourceError] = useState("");
    const [requestError, setRequestError] = useState("");

    const [submittingResource, setSubmittingResource] = useState(false);
    const [processingBooking, setProcessingBooking] = useState(null);
    const [successMessage, setSuccessMessage] = useState("");

    const [activeInspection, setActiveInspection] = useState(null);

    const [inspectionsByBooking, setInspectionsByBooking] = useState({});
    const [activeComparisonBooking, setActiveComparisonBooking] = useState(null);

    const [resourceInspectionImages, setResourceInspectionImages] = useState(null);
    const [showResourceInspection, setShowResourceInspection] = useState(false);
    const [resourceUploadProgress, setResourceUploadProgress] = useState("");

    // Retains the created resource ID and completed uploads if an upload fails.
    // This prevents creating duplicate resources when retrying the image upload.
    const pendingResourceUploadRef = useRef(null);

    // React state controls the button label during rendering.
    const [hasPendingResourceUpload, setHasPendingResourceUpload] =
        useState(false);

    const [newResource, setNewResource] = useState({
        title: "",
        description: "",
        category: "Electronics",
        location: "",
        resource_type: "EQUIPMENT",
        usage_rules: "",
    });

    function moveHighlight(element) {
        if (!element || !navRef.current) return;

        setHighlightStyle({
            top: element.offsetTop,
            height: element.offsetHeight,
        });
    }

    function handleNavClick(id) {
        setActiveNav(id);
        setIsNavOpen(false);

        document.getElementById(id)?.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }

    useEffect(() => {
        function handleEscape(event) {
            if (event.key === "Escape") setIsNavOpen(false);
        }

        window.addEventListener("keydown", handleEscape);

        return () => window.removeEventListener("keydown", handleEscape);
    }, []);

    useEffect(() => {
        if (!isNavOpen) return;

        const activeElement = navRef.current?.querySelector(
            `[data-nav-id="${activeNav}"]`
        );

        if (activeElement) moveHighlight(activeElement);
    }, [isNavOpen, activeNav]);

    useEffect(() => {
        if (!user?.id) return;

        let cancelled = false;

        async function loadDashboard() {
            const resourceRequest = apiRequest("/resources?skip=0&limit=100")
                .then((response) => {
                    if (!Array.isArray(response)) {
                        throw new Error("Unexpected resources response from server.");
                    }

                    if (!cancelled) {
                        setResources(
                            response.filter(
                                (resource) =>
                                    Number(resource.owner_id) === Number(user.id)
                            )
                        );
                        setResourceError("");
                    }
                })
                .catch((error) => {
                    console.error("Owner resources error:", error);

                    if (!cancelled) {
                        setResourceError(
                            formatApiError(error, "Unable to load resources.")
                        );
                    }
                })
                .finally(() => {
                    if (!cancelled) setLoadingResources(false);
                });

            const bookingRequest = apiRequest("/bookings/owner")
                .then((response) => {
                    const bookingData = response.data ?? response;

                    if (!Array.isArray(bookingData)) {
                        throw new Error("Unexpected booking response from server.");
                    }

                    if (!cancelled) {
                        setRequests(bookingData);
                        setRequestError("");
                    }
                })
                .catch((error) => {
                    console.error("Owner booking error:", error);

                    if (!cancelled) {
                        setRequestError(
                            formatApiError(error, "Unable to load booking requests.")
                        );
                    }
                })
                .finally(() => {
                    if (!cancelled) setLoadingRequests(false);
                });

            await Promise.all([resourceRequest, bookingRequest]);
        }

        void loadDashboard();

        return () => {
            cancelled = true;
        };
    }, [user?.id]);

    const fetchResources = useCallback(async () => {
        try {
            const response = await apiRequest("/resources?skip=0&limit=100");

            if (!Array.isArray(response)) {
                throw new Error("Unexpected resources response from server.");
            }

            setResources(
                response.filter(
                    (resource) => Number(resource.owner_id) === Number(user?.id)
                )
            );

            setResourceError("");
        } catch (error) {
            console.error("Owner resources error:", error);
            setResourceError(formatApiError(error, "Unable to load resources."));
        } finally {
            setLoadingResources(false);
        }
    }, [user?.id]);

    const fetchRequests = useCallback(async () => {
        try {
            const response = await apiRequest("/bookings/owner");
            const bookingData = response.data ?? response;

            if (!Array.isArray(bookingData)) {
                throw new Error("Unexpected booking response from server.");
            }

            setRequests(bookingData);
            setRequestError("");
        } catch (error) {
            console.error("Owner booking error:", error);
            setRequestError(
                formatApiError(error, "Unable to load booking requests.")
            );
        } finally {
            setLoadingRequests(false);
        }
    }, []);

    const filteredResources = resources.filter((resource) =>
        resource.title?.toLowerCase().includes(search.toLowerCase())
    );

    const pendingCount = requests.filter(
        (request) => request.status?.toUpperCase() === "PENDING"
    ).length;

    const approvedCount = requests.filter(
        (request) => request.status?.toUpperCase() === "APPROVED"
    ).length;

    async function uploadResourceImages(resourceId, imageFiles) {
        const pending = pendingResourceUploadRef.current;

        if (
            !pending ||
            Number(pending.resourceId) !== Number(resourceId)
        ) {
            pendingResourceUploadRef.current = {
                resourceId,
                uploadedAngles: [],
            };

            setHasPendingResourceUpload(true);
        }

        const uploadSession = pendingResourceUploadRef.current;

        for (let index = 0; index < RESOURCE_IMAGE_ANGLES.length; index += 1) {
            const angle = RESOURCE_IMAGE_ANGLES[index];

            if (uploadSession.uploadedAngles.includes(angle)) {
                continue;
            }

            const file = imageFiles[angle];

            if (!file) {
                throw new Error(`The ${angle} resource photo is missing.`);
            }

            setResourceUploadProgress(
                `Uploading ${angle.toLowerCase()} photo (${index + 1}/6)...`
            );

            const formData = new FormData();
            formData.append("file", file);
            formData.append("is_primary", index === 0 ? "true" : "false");

            await apiRequest(`/resources/${resourceId}/images`, {
                method: "POST",
                body: formData,
            });

            uploadSession.uploadedAngles.push(angle);
        }

        pendingResourceUploadRef.current = null;
        setHasPendingResourceUpload(false);
    }

    async function handleAddResource(event) {
        event.preventDefault();

        try {
            setSubmittingResource(true);
            setResourceError("");
            setSuccessMessage("");
            setResourceUploadProgress("");

            const payload = {
                title: newResource.title.trim(),
                description: newResource.description.trim(),
                category: newResource.category,
                resource_type: newResource.resource_type,
                location: newResource.location.trim(),
                usage_rules: newResource.usage_rules.trim(),
            };

            let resourceId = editingResourceId;

            if (editingResourceId) {
                await apiRequest(`/resources/${editingResourceId}`, {
                    method: "PATCH",
                    body: JSON.stringify(payload),
                });
            } else {
                const pending = pendingResourceUploadRef.current;

                // If resource creation already succeeded but image uploads failed,
                // retry uploads against that resource instead of creating another.
                if (
                    pending &&
                    pending.title === payload.title &&
                    Number(pending.ownerId) === Number(user?.id)
                ) {
                    resourceId = pending.resourceId;
                } else {
                    setResourceUploadProgress("Publishing resource...");

                    const response = await apiRequest("/resources", {
                        method: "POST",
                        body: JSON.stringify(payload),
                    });

                    resourceId = getResourceId(response);

                    if (resourceId === null) {
                        throw new Error(
                            "The resource may have been created, but its ID was not returned. Check My Resources before submitting again."
                        );
                    }

                    if (resourceInspectionImages) {
                        pendingResourceUploadRef.current = {
                            resourceId,
                            title: payload.title,
                            ownerId: user?.id,
                            uploadedAngles: [],
                        };

                        setHasPendingResourceUpload(true);
                    }
                }

                if (resourceInspectionImages) {
                    await uploadResourceImages(
                        resourceId,
                        resourceInspectionImages
                    );
                }
            }

            setNewResource({
                title: "",
                description: "",
                category: "Electronics",
                location: "",
                resource_type: "EQUIPMENT",
                usage_rules: "",
            });

            setResourceInspectionImages(null);
            setShowResourceInspection(false);
            setEditingResourceId(null);
            setShowForm(false);
            setResourceUploadProgress("");
            pendingResourceUploadRef.current = null;
            setHasPendingResourceUpload(false);

            setSuccessMessage(
                editingResourceId
                    ? "Resource updated successfully."
                    : resourceInspectionImages
                        ? "Resource published and all six photos uploaded successfully."
                        : "Resource published successfully."
            );

            setLoadingResources(true);
            await fetchResources();
        } catch (error) {
            console.error(
                editingResourceId
                    ? "Update resource error:"
                    : "Create resource or image upload error:",
                error
            );

            setResourceError(
                formatApiError(
                    error,
                    "Unable to complete the resource operation."
                )
            );
        } finally {
            setSubmittingResource(false);
        }
    }

    function startEditingResource(resource) {
        setNewResource({
            title: resource.title || "",
            description: resource.description || "",
            category: resource.category || "Other",
            location: resource.location || "",
            resource_type: resource.resource_type || "EQUIPMENT",
            usage_rules: resource.usage_rules || "",
        });

        setResourceInspectionImages(null);
        setShowResourceInspection(false);
        setEditingResourceId(resource.id);
        setShowForm(true);
        setResourceError("");
        setResourceUploadProgress("");
    }

    function resetResourceForm() {
        setNewResource({
            title: "",
            description: "",
            category: "Electronics",
            location: "",
            resource_type: "EQUIPMENT",
            usage_rules: "",
        });

        setResourceInspectionImages(null);
        setShowResourceInspection(false);
        setEditingResourceId(null);
        setShowForm(false);
        setResourceError("");
        setResourceUploadProgress("");
    }

    async function handleRequest(bookingId, decision) {
        let reason = null;

        if (decision === "REJECTED") {
            reason = window.prompt("Enter a rejection reason (optional):");
            if (reason === null) return;
        }

        try {
            setProcessingBooking(bookingId);
            setRequestError("");
            setSuccessMessage("");

            await apiRequest(`/bookings/${bookingId}/decision`, {
                method: "PATCH",
                body: JSON.stringify({
                    decision,
                    reason: reason?.trim() || null,
                }),
            });

            setSuccessMessage(
                `Booking #${bookingId} ${decision.toLowerCase()} successfully.`
            );

            setLoadingRequests(true);
            await fetchRequests();
        } catch (error) {
            console.error("Booking decision error:", error);
            setRequestError(formatApiError(error, "Unable to update booking."));
        } finally {
            setProcessingBooking(null);
        }
    }

    function handleLogout() {
        logout();
        navigate("/login", { replace: true });
    }

    const resourceMap = new Map(
        resources.map((resource) => [Number(resource.id), resource])
    );

    return (
        <div className="owner-dashboard">
            <button
                type="button"
                className={`ob-menu-btn ${isNavOpen ? "is-open" : ""}`}
                onClick={() => setIsNavOpen((previous) => !previous)}
                aria-label={isNavOpen ? "Close navigation" : "Open navigation"}
                aria-expanded={isNavOpen}
                aria-controls="owner-navigation"
            >
                <span />
                <span />
                <span />
            </button>

            <div
                className={`ob-nav-scrim ${isNavOpen ? "visible" : ""}`}
                onClick={() => setIsNavOpen(false)}
                aria-hidden="true"
            />

            <aside
                className={`ob-sidebar ${isNavOpen ? "visible" : ""}`}
                id="owner-navigation"
                aria-label="Owner navigation"
            >
                <div className="ob-brand">OpenBench.</div>
                <p className="ob-menu-label">OWNER PORTAL</p>

                <nav className="ob-links" ref={navRef}>
                    <div
                        className="ob-follow"
                        style={{
                            transform: `translateY(${highlightStyle.top}px)`,
                            height: `${highlightStyle.height}px`,
                        }}
                    />

                    <button
                        type="button"
                        className={`ob-item ${activeNav === "overview" ? "active" : ""}`}
                        data-nav-id="overview"
                        onMouseEnter={(event) => moveHighlight(event.currentTarget)}
                        onFocus={(event) => moveHighlight(event.currentTarget)}
                        onClick={() => handleNavClick("overview")}
                    >
                        <LayoutDashboard size={19} />
                        Dashboard
                    </button>

                    <button
                        type="button"
                        className={`ob-item ${activeNav === "my-resources" ? "active" : ""}`}
                        data-nav-id="my-resources"
                        onMouseEnter={(event) => moveHighlight(event.currentTarget)}
                        onFocus={(event) => moveHighlight(event.currentTarget)}
                        onClick={() => handleNavClick("my-resources")}
                    >
                        <Package size={19} />
                        My Resources
                    </button>

                    <button
                        type="button"
                        className={`ob-item ${activeNav === "requests" ? "active" : ""}`}
                        data-nav-id="requests"
                        onMouseEnter={(event) => moveHighlight(event.currentTarget)}
                        onFocus={(event) => moveHighlight(event.currentTarget)}
                        onClick={() => handleNavClick("requests")}
                    >
                        <CalendarDays size={19} />
                        Booking Requests
                    </button>
                </nav>

                <div className="ob-sidebar-bottom">
                    <div className="ob-profile">
                        <div className="ob-avatar">
                            {user?.full_name?.charAt(0)?.toUpperCase() || "O"}
                        </div>

                        <div>
                            <strong>{user?.full_name || "Owner"}</strong>
                            <span>Resource Owner</span>
                        </div>
                    </div>

                    <button
                        type="button"
                        className="ob-logout"
                        onClick={() => {
                            setIsNavOpen(false);
                            handleLogout();
                        }}
                    >
                        <LogOut size={18} />
                        Logout
                    </button>
                </div>
            </aside>

            <main className="owner-main">
                <header className="owner-header" id="overview">
                    <div>
                        <p className="owner-eyebrow">RESOURCE MANAGEMENT</p>
                        <h1>Owner Dashboard</h1>
                        <p className="owner-muted">
                            Manage your campus resources and booking requests.
                        </p>
                    </div>

                    <button
                        className="add-resource-button"
                        onClick={() => {
                            if (showForm && editingResourceId === null) {
                                resetResourceForm();
                                return;
                            }

                            resetResourceForm();
                            setShowForm(true);
                            setResourceError("");
                        }}
                    >
                        <Plus size={18} />
                        {showForm && editingResourceId === null
                            ? "Close Form"
                            : "Add Resource"}
                    </button>
                </header>

                {successMessage && (
                    <p className="owner-success-message">
                        <CheckCircle size={17} />
                        {successMessage}
                    </p>
                )}

                <section className="owner-stats">
                    <div className="owner-stat-card">
                        <Package size={22} />
                        <span>Total Resources</span>
                        <h2>{loadingResources ? "..." : resources.length}</h2>
                    </div>

                    <div className="owner-stat-card">
                        <CalendarDays size={22} />
                        <span>Total Requests</span>
                        <h2>{loadingRequests ? "..." : requests.length}</h2>
                    </div>

                    <div className="owner-stat-card">
                        <Clock size={22} />
                        <span>Pending Requests</span>
                        <h2>{loadingRequests ? "..." : pendingCount}</h2>
                    </div>
                </section>

                {showForm && (
                    <section className="owner-form-section" id="resource-form">
                        <h2>
                            {editingResourceId
                                ? "Edit Resource"
                                : "Add a New Resource"}
                        </h2>

                        <form onSubmit={handleAddResource}>
                            <label>Resource name</label>
                            <input
                                required
                                minLength={2}
                                placeholder="Example: DSLR Camera"
                                value={newResource.title}
                                onChange={(event) =>
                                    setNewResource({
                                        ...newResource,
                                        title: event.target.value,
                                    })
                                }
                            />

                            <label>Description</label>
                            <textarea
                                placeholder="Describe your resource..."
                                value={newResource.description}
                                onChange={(event) =>
                                    setNewResource({
                                        ...newResource,
                                        description: event.target.value,
                                    })
                                }
                            />

                            <label>Resource type</label>
                            <select
                                value={newResource.resource_type}
                                onChange={(event) =>
                                    setNewResource({
                                        ...newResource,
                                        resource_type: event.target.value,
                                    })
                                }
                            >
                                <option value="EQUIPMENT">Equipment</option>
                                <option value="SPACE">Campus Space</option>
                            </select>

                            <label>Category</label>
                            <select
                                value={newResource.category}
                                onChange={(event) =>
                                    setNewResource({
                                        ...newResource,
                                        category: event.target.value,
                                    })
                                }
                            >
                                <option>Electronics</option>
                                <option>Photography</option>
                                <option>Campus Space</option>
                                <option>Sports</option>
                                <option>Other</option>
                            </select>

                            <label>Location</label>
                            <input
                                required
                                placeholder="Example: Library, Floor 2"
                                value={newResource.location}
                                onChange={(event) =>
                                    setNewResource({
                                        ...newResource,
                                        location: event.target.value,
                                    })
                                }
                            />

                            <label>Usage rules</label>
                            <textarea
                                placeholder="Enter rules for using this resource..."
                                value={newResource.usage_rules}
                                onChange={(event) =>
                                    setNewResource({
                                        ...newResource,
                                        usage_rules: event.target.value,
                                    })
                                }
                            />

                            {!editingResourceId && (
                                <div className="resource-inspection-section">
                                    <h3>Resource Photos</h3>

                                    <p>
                                        Add six photos to your resource gallery.
                                        The FRONT photo will be the primary image.
                                    </p>

                                    <p>
                                        Required views: Front, Back, Left, Right,
                                        Top and Bottom.
                                    </p>

                                    {resourceInspectionImages ? (
                                        <div>
                                            <p>
                                                <CheckCircle size={16} />
                                                Six photos selected and ready
                                                for upload.
                                            </p>

                                            <button
                                                type="button"
                                                className="resource-action"
                                                onClick={() => {
                                                    setShowResourceInspection(true);
                                                    setResourceError("");
                                                }}
                                            >
                                                <Camera size={16} />
                                                Review or Replace Photos
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            type="button"
                                            className="resource-action"
                                            onClick={() => {
                                                setShowResourceInspection(true);
                                                setResourceError("");
                                            }}
                                        >
                                            <Camera size={16} />
                                            Select Six Photos
                                        </button>
                                    )}

                                    {showResourceInspection && (
                                        <InspectionCapture
                                            reportType="initial"
                                            onCancel={() =>
                                                setShowResourceInspection(false)
                                            }
                                            onComplete={({ images }) => {
                                                setResourceInspectionImages(images);
                                                setShowResourceInspection(false);
                                                setResourceError("");
                                            }}
                                        />
                                    )}

                                    <p className="owner-muted">
                                        Images are uploaded after the resource
                                        is created. Keep this form open if an
                                        upload needs to be retried.
                                    </p>
                                </div>
                            )}

                            {resourceUploadProgress && (
                                <p className="owner-muted" role="status">
                                    {resourceUploadProgress}
                                </p>
                            )}

                            {resourceError && (
                                <p className="owner-error-message" role="alert">
                                    {resourceError}
                                </p>
                            )}

                            <div className="owner-form-actions">
                                <button
                                    type="submit"
                                    disabled={submittingResource}
                                >
                                    {submittingResource
                                        ? "Saving..."
                                        : editingResourceId
                                            ? "Save Changes"
                                            : hasPendingResourceUpload
                                                ? "Retry Photo Upload"
                                                : "Publish Resource"}
                                </button>

                                <button
                                    type="button"
                                    className="cancel-button"
                                    onClick={resetResourceForm}
                                    disabled={submittingResource}
                                >
                                    Cancel
                                </button>
                            </div>
                        </form>
                    </section>
                )}

                <section className="owner-resources" id="my-resources">
                    <div className="owner-section-heading">
                        <div>
                            <p className="owner-eyebrow">YOUR LISTINGS</p>
                            <h2>My Resources</h2>
                        </div>

                        <div className="owner-search">
                            <Search size={17} />
                            <input
                                placeholder="Search resources..."
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                            />
                        </div>
                    </div>

                    {resourceError && !showForm && (
                        <p className="owner-error-message">{resourceError}</p>
                    )}

                    <div className="owner-resource-grid">
                        {loadingResources && (
                            <p className="owner-muted">Loading your resources...</p>
                        )}

                        {!loadingResources &&
                            filteredResources.map((resource) => {
                                const Icon = getResourceIcon(resource);

                                return (
                                    <article
                                        className="owner-resource-card"
                                        key={resource.id}
                                    >
                                        <ResourceImage
                                            resource={resource}
                                            fallbackIcon={<Icon size={42} />}
                                            className="owner-resource-image"
                                            height={150}
                                        />

                                        <span className="owner-resource-category">
                                            {resource.category}
                                        </span>

                                        <h3>{resource.title}</h3>

                                        <p className="owner-resource-location">
                                            <MapPin size={15} />
                                            {resource.location}
                                        </p>

                                        <span
                                            className={
                                                resource.is_active
                                                    ? "owner-status available-status"
                                                    : "owner-status unavailable-status"
                                            }
                                        >
                                            {resource.is_active
                                                ? "Available"
                                                : "Unavailable"}
                                        </span>

                                        <button
                                            type="button"
                                            className="resource-action"
                                            onClick={() =>
                                                startEditingResource(resource)
                                            }
                                        >
                                            Edit Resource
                                        </button>
                                    </article>
                                );
                            })}

                        {!loadingResources &&
                            !resourceError &&
                            filteredResources.length === 0 && (
                                <p className="owner-muted">
                                    {resources.length === 0
                                        ? "You haven't published any resources yet."
                                        : "No matching resources found."}
                                </p>
                            )}
                    </div>

                    <button
                        className="resource-action"
                        onClick={() => {
                            setLoadingResources(true);
                            fetchResources();
                        }}
                        disabled={loadingResources}
                    >
                        <RefreshCw size={15} />
                        Refresh Resources
                    </button>
                </section>

                <section className="owner-requests" id="requests">
                    <div className="owner-section-heading">
                        <div>
                            <p className="owner-eyebrow">STUDENT ACTIVITY</p>
                            <h2>Booking Requests</h2>
                            <p className="owner-muted">
                                Approved requests: {approvedCount}
                            </p>
                        </div>
                    </div>

                    {requestError && (
                        <p className="owner-error-message">{requestError}</p>
                    )}

                    <div className="request-list">
                        {loadingRequests && (
                            <p className="owner-muted">
                                Loading booking requests...
                            </p>
                        )}

                        {!loadingRequests &&
                            requests.map((request) => {
                                const resource = resourceMap.get(
                                    Number(request.resource_id)
                                );

                                const status =
                                    request.status?.toUpperCase() || "UNKNOWN";

                                const isPending = status === "PENDING";
                                const isProcessing =
                                    processingBooking === request.id;

                                const bookingInspections =
                                    inspectionsByBooking[request.id];

                                const hasBothInspections = Boolean(
                                    bookingInspections?.initial &&
                                    bookingInspections?.final
                                );

                                return (
                                    <article
                                        className="request-card"
                                        key={request.id}
                                    >
                                        <div className="request-details">
                                            <h3>
                                                {resource?.title ||
                                                    `Resource #${request.resource_id}`}
                                            </h3>

                                            <p>
                                                Requested by Student #{request.user_id}
                                            </p>

                                            <span>
                                                <CalendarDays size={14} />
                                                {formatDate(request.start_at)}
                                            </span>

                                            <span>
                                                <Clock size={14} />
                                                {formatTime(request.start_at)} –{" "}
                                                {formatTime(request.end_at)}
                                            </span>

                                            <p>
                                                <strong>Purpose:</strong>{" "}
                                                {request.purpose}
                                            </p>

                                            {request.reason && (
                                                <p>
                                                    <strong>Decision note:</strong>{" "}
                                                    {request.reason}
                                                </p>
                                            )}
                                        </div>

                                        <div className="request-actions">
                                            <span
                                                className={`request-status ${status.toLowerCase()}`}
                                            >
                                                {getStatusLabel(status)}
                                            </span>

                                            {isPending && (
                                                <>
                                                    <button
                                                        className="approve-button"
                                                        disabled={isProcessing}
                                                        onClick={() =>
                                                            handleRequest(
                                                                request.id,
                                                                "APPROVED"
                                                            )
                                                        }
                                                    >
                                                        <CheckCircle size={15} />
                                                        {isProcessing
                                                            ? "Processing..."
                                                            : "Approve"}
                                                    </button>

                                                    <button
                                                        className="reject-button"
                                                        disabled={isProcessing}
                                                        onClick={() =>
                                                            handleRequest(
                                                                request.id,
                                                                "REJECTED"
                                                            )
                                                        }
                                                    >
                                                        <XCircle size={15} />
                                                        Reject
                                                    </button>
                                                </>
                                            )}

                                            {status === "APPROVED" && (
                                                <button
                                                    className="approve-button"
                                                    onClick={() =>
                                                        setActiveInspection({
                                                            bookingId: request.id,
                                                            reportType: "initial",
                                                        })
                                                    }
                                                >
                                                    <Camera size={15} />
                                                    Initial Inspection
                                                </button>
                                            )}

                                            {status === "IN_USE" && (
                                                <button
                                                    className="approve-button"
                                                    onClick={() =>
                                                        setActiveInspection({
                                                            bookingId: request.id,
                                                            reportType: "final",
                                                        })
                                                    }
                                                >
                                                    <Camera size={15} />
                                                    Final Inspection
                                                </button>
                                            )}

                                            {hasBothInspections && (
                                                <button
                                                    type="button"
                                                    className="approve-button"
                                                    onClick={() =>
                                                        setActiveComparisonBooking(
                                                            request.id
                                                        )
                                                    }
                                                >
                                                    Compare Inspections
                                                </button>
                                            )}
                                        </div>

                                        {activeInspection?.bookingId === request.id && (
                                            <InspectionCapture
                                                bookingId={request.id}
                                                reportType={activeInspection.reportType}
                                                onCancel={() =>
                                                    setActiveInspection(null)
                                                }
                                                onComplete={({
                                                    reportType,
                                                    description,
                                                    images,
                                                    reportId,
                                                    savedToBackend,
                                                }) => {
                                                    setInspectionsByBooking(
                                                        (previous) => ({
                                                            ...previous,
                                                            [request.id]: {
                                                                ...previous[request.id],
                                                                [reportType]: {
                                                                    description,
                                                                    images,
                                                                    reportId,
                                                                    savedToBackend,
                                                                },
                                                            },
                                                        })
                                                    );

                                                    setSuccessMessage(
                                                        `${reportType === "initial" ? "Initial" : "Final"} inspection saved successfully.`
                                                    );

                                                    setActiveInspection(null);
                                                }}
                                            />
                                        )}

                                        {activeComparisonBooking === request.id &&
                                            hasBothInspections && (
                                                <InspectionComparison
                                                    initialInspection={
                                                        bookingInspections.initial
                                                    }
                                                    finalInspection={
                                                        bookingInspections.final
                                                    }
                                                    reviewed={
                                                        bookingInspections.reviewed ||
                                                        false
                                                    }
                                                    onReviewed={() => {
                                                        setInspectionsByBooking(
                                                            (previous) => ({
                                                                ...previous,
                                                                [request.id]: {
                                                                    ...previous[
                                                                    request.id
                                                                    ],
                                                                    reviewed: true,
                                                                },
                                                            })
                                                        );
                                                    }}
                                                    onClose={() =>
                                                        setActiveComparisonBooking(
                                                            null
                                                        )
                                                    }
                                                />
                                            )}
                                    </article>
                                );
                            })}

                        {!loadingRequests &&
                            !requestError &&
                            requests.length === 0 && (
                                <p className="owner-muted">
                                    No booking requests yet.
                                </p>
                            )}
                    </div>

                    <button
                        className="resource-action"
                        onClick={() => {
                            setLoadingRequests(true);
                            fetchRequests();
                        }}
                        disabled={loadingRequests}
                    >
                        <RefreshCw size={15} />
                        Refresh Requests
                    </button>
                </section>

                <p className="owner-demo-note">
                    Resources, resource images and booking requests are connected
                    to the OpenBench backend. Inspection reports and their
                    uploaded photos are sent to the backend. Inspection
                    comparison results currently remain session-only.
                </p>
            </main>
        </div>
    );
}
