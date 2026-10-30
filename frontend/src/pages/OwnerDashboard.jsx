
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

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

import { useAuth } from "../context/AuthContext";
import { apiRequest } from "../api/client";
import "./OwnerDashboard.css";

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

    // Navigation state
    const [isNavOpen, setIsNavOpen] = useState(false);
    const [activeNav, setActiveNav] = useState("overview");
    const [highlightStyle, setHighlightStyle] = useState({
        top: 0,
        height: 56,
    });

    const navRef = useRef(null);

    // Dashboard state
    const [resources, setResources] = useState([]);
    const [requests, setRequests] = useState([]);

    const [search, setSearch] = useState("");
    const [showForm, setShowForm] = useState(false);

    const [loadingResources, setLoadingResources] = useState(true);
    const [loadingRequests, setLoadingRequests] = useState(true);

    const [resourceError, setResourceError] = useState("");
    const [requestError, setRequestError] = useState("");

    const [submittingResource, setSubmittingResource] = useState(false);
    const [processingBooking, setProcessingBooking] = useState(null);
    const [successMessage, setSuccessMessage] = useState("");

    const [newResource, setNewResource] = useState({
        title: "",
        description: "",
        category: "Electronics",
        location: "",
        resource_type: "EQUIPMENT",
        usage_rules: "",
    });

    // Move the animated blue highlight.
    function moveHighlight(element) {
        if (!element || !navRef.current) return;

        setHighlightStyle({
            top: element.offsetTop,
            height: element.offsetHeight,
        });
    }

    // Navigate to a dashboard section.
    function handleNavClick(id) {
        setActiveNav(id);
        setIsNavOpen(false);

        const section = document.getElementById(id);

        section?.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }

    // Keyboard support.
    useEffect(() => {
        function handleEscape(event) {
            if (event.key === "Escape") {
                setIsNavOpen(false);
            }
        }

        window.addEventListener("keydown", handleEscape);

        return () => {
            window.removeEventListener("keydown", handleEscape);
        };
    }, []);

    // Position highlight on the active item when menu opens.
    useEffect(() => {
        if (!isNavOpen) return;

        const activeElement = navRef.current?.querySelector(
            `[data-nav-id="${activeNav}"]`
        );

        if (activeElement) {
            moveHighlight(activeElement);
        }
    }, [isNavOpen, activeNav]);

    // Load resources belonging to the logged-in owner.
    async function fetchResources() {
        try {
            setLoadingResources(true);
            setResourceError("");

            const response = await apiRequest("/resources?skip=0&limit=100");

            if (!Array.isArray(response)) {
                throw new Error("Unexpected resources response from server.");
            }

            const ownerResources = response.filter(
                (resource) => Number(resource.owner_id) === Number(user?.id)
            );

            setResources(ownerResources);
        } catch (error) {
            console.error("Owner resources error:", error);
            setResourceError(error.message || "Unable to load resources.");
        } finally {
            setLoadingResources(false);
        }
    }

    // Load booking requests for this owner.
    async function fetchRequests() {
        try {
            setLoadingRequests(true);
            setRequestError("");

            const response = await apiRequest("/bookings/owner");
            const bookingData = response.data ?? response;

            if (!Array.isArray(bookingData)) {
                throw new Error("Unexpected booking response from server.");
            }

            setRequests(bookingData);
        } catch (error) {
            console.error("Owner booking error:", error);
            setRequestError(error.message || "Unable to load booking requests.");
        } finally {
            setLoadingRequests(false);
        }
    }

    useEffect(() => {
        if (user?.id) {
            fetchResources();
            fetchRequests();
        }
    }, [user?.id]);

    // Search resources.
    const filteredResources = resources.filter((resource) =>
        resource.title?.toLowerCase().includes(search.toLowerCase())
    );

    const pendingCount = requests.filter(
        (request) => request.status?.toUpperCase() === "PENDING"
    ).length;

    const approvedCount = requests.filter(
        (request) => request.status?.toUpperCase() === "APPROVED"
    ).length;

    // Create resource through backend.
    async function handleAddResource(event) {
        event.preventDefault();

        try {
            setSubmittingResource(true);
            setResourceError("");
            setSuccessMessage("");

            const payload = {
                title: newResource.title.trim(),
                description: newResource.description.trim(),
                category: newResource.category,
                resource_type: newResource.resource_type,
                location: newResource.location.trim(),
                usage_rules: newResource.usage_rules.trim(),
            };

            await apiRequest("/resources", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            setNewResource({
                title: "",
                description: "",
                category: "Electronics",
                location: "",
                resource_type: "EQUIPMENT",
                usage_rules: "",
            });

            setShowForm(false);
            setSuccessMessage("Resource published successfully.");

            await fetchResources();
        } catch (error) {
            console.error("Create resource error:", error);
            setResourceError(error.message || "Unable to create resource.");
        } finally {
            setSubmittingResource(false);
        }
    }

    // Approve or reject a booking through backend.
    async function handleRequest(bookingId, decision) {
        let reason = null;

        if (decision === "REJECTED") {
            reason = window.prompt(
                "Enter a rejection reason (optional):"
            );

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

            await fetchRequests();
        } catch (error) {
            console.error("Booking decision error:", error);
            setRequestError(error.message || "Unable to update booking.");
        } finally {
            setProcessingBooking(null);
        }
    }

    function handleLogout() {
        logout();
        navigate("/login", { replace: true });
    }

    const resourceMap = new Map(
        resources.map((resource) => [
            Number(resource.id),
            resource,
        ])
    );

    return (
        <div className="owner-dashboard">

            {/* ANIMATED HAMBURGER BUTTON */}
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

            {/* BACKGROUND OVERLAY */}
            <div
                className={`ob-nav-scrim ${isNavOpen ? "visible" : ""}`}
                onClick={() => setIsNavOpen(false)}
                aria-hidden="true"
            />

            {/* ANIMATED GLASS NAVIGATION */}
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
                        onMouseEnter={(event) =>
                            moveHighlight(event.currentTarget)
                        }
                        onFocus={(event) =>
                            moveHighlight(event.currentTarget)
                        }
                        onClick={() => handleNavClick("overview")}
                    >
                        <LayoutDashboard size={19} />
                        Dashboard
                    </button>

                    <button
                        type="button"
                        className={`ob-item ${activeNav === "my-resources" ? "active" : ""}`}
                        data-nav-id="my-resources"
                        onMouseEnter={(event) =>
                            moveHighlight(event.currentTarget)
                        }
                        onFocus={(event) =>
                            moveHighlight(event.currentTarget)
                        }
                        onClick={() => handleNavClick("my-resources")}
                    >
                        <Package size={19} />
                        My Resources
                    </button>

                    <button
                        type="button"
                        className={`ob-item ${activeNav === "requests" ? "active" : ""}`}
                        data-nav-id="requests"
                        onMouseEnter={(event) =>
                            moveHighlight(event.currentTarget)
                        }
                        onFocus={(event) =>
                            moveHighlight(event.currentTarget)
                        }
                        onClick={() => handleNavClick("requests")}
                    >
                        <CalendarDays size={19} />
                        Booking Requests
                    </button>
                </nav>

                {/* PROFILE AND LOGOUT */}
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

            {/* MAIN DASHBOARD */}
            <main className="owner-main">

                {/* HEADER */}
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
                        onClick={() => setShowForm(!showForm)}
                    >
                        <Plus size={18} />
                        Add Resource
                    </button>
                </header>

                {successMessage && (
                    <p className="owner-success-message">
                        <CheckCircle size={17} />
                        {successMessage}
                    </p>
                )}

                {/* STATISTICS */}
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

                {/* ADD RESOURCE FORM */}
                {showForm && (
                    <section className="owner-form-section">
                        <h2>Add a New Resource</h2>

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

                            <div className="owner-form-actions">
                                <button
                                    type="submit"
                                    disabled={submittingResource}
                                >
                                    {submittingResource
                                        ? "Publishing..."
                                        : "Publish Resource"}
                                </button>

                                <button
                                    type="button"
                                    className="cancel-button"
                                    onClick={() => setShowForm(false)}
                                >
                                    Cancel
                                </button>
                            </div>
                        </form>
                    </section>
                )}

                {/* MY RESOURCES */}
                <section
                    className="owner-resources"
                    id="my-resources"
                >
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
                                onChange={(event) =>
                                    setSearch(event.target.value)
                                }
                            />
                        </div>
                    </div>

                    {resourceError && (
                        <p className="owner-error-message">
                            {resourceError}
                        </p>
                    )}

                    <div className="owner-resource-grid">
                        {loadingResources && (
                            <p className="owner-muted">
                                Loading your resources...
                            </p>
                        )}

                        {!loadingResources &&
                            filteredResources.map((resource) => {
                                const Icon = getResourceIcon(resource);

                                return (
                                    <article
                                        className="owner-resource-card"
                                        key={resource.id}
                                    >
                                        <div className="owner-resource-icon">
                                            <Icon size={27} />
                                        </div>

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
                        onClick={fetchResources}
                        disabled={loadingResources}
                    >
                        <RefreshCw size={15} />
                        Refresh Resources
                    </button>
                </section>

                {/* BOOKING REQUESTS */}
                <section
                    className="owner-requests"
                    id="requests"
                >
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
                        <p className="owner-error-message">
                            {requestError}
                        </p>
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
                                        </div>
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
                        onClick={fetchRequests}
                        disabled={loadingRequests}
                    >
                        <RefreshCw size={15} />
                        Refresh Requests
                    </button>
                </section>

                <p className="owner-demo-note">
                    Resources and booking requests are connected to the OpenBench backend.
                </p>
            </main>
        </div>
    );
}
