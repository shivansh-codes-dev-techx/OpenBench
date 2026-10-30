
import { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";

import {
    Search,
    Laptop,
    Monitor,
    Camera,
    Armchair,
    CalendarDays,
    Clock,
    MapPin,
    ArrowRight,
    LogOut,
    LayoutDashboard,
    Package,
    RefreshCw,
    ClipboardCheck,
    LogIn,
    LogOut as CheckOutIcon,
} from "lucide-react";

import { useAuth } from "../context/useAuth";
import { apiRequest } from "../api/client";
import "./StudentDashboard.css";

const API_BASE_URL = (
    import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

function getResourceIcon(resource) {
    const type = resource.resource_type?.toUpperCase();
    const category = resource.category?.toLowerCase() || "";
    const title = resource.title?.toLowerCase() || "";

    if (type === "SPACE") return Armchair;
    if (title.includes("camera") || category.includes("photography")) return Camera;
    if (title.includes("projector") || title.includes("monitor")) return Monitor;

    return Laptop;
}

function formatDateTime(value) {
    if (!value) return "Not available";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not available";

    return date.toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
    });
}

function getStatusClass(status) {
    switch (status?.toUpperCase()) {
        case "APPROVED":
        case "IN_USE":
        case "RETURNED":
            return "approved";
        case "REJECTED":
            return "rejected";
        case "PENDING":
            return "pending";
        default:
            return "unknown";
    }
}

function getApiError(error) {
    if (Array.isArray(error?.message)) {
        return error.message
            .map((item) => item.msg || item.message || "Validation error")
            .join(", ");
    }

    return error?.message || "Something went wrong. Please try again.";
}

function getSavedReportFlags() {
    try {
        return JSON.parse(localStorage.getItem("openbench_report_flags") || "{}");
    } catch {
        return {};
    }
}

export default function StudentDashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const [isNavOpen, setIsNavOpen] = useState(false);
    const [activeNav, setActiveNav] = useState("overview");
    const navRef = useRef(null);

    const [resources, setResources] = useState([]);
    const [bookings, setBookings] = useState([]);

    const [search, setSearch] = useState("");
    const [category, setCategory] = useState("All");

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const [bookingsLoading, setBookingsLoading] = useState(true);
    const [bookingError, setBookingError] = useState("");

    const [actionLoading, setActionLoading] = useState({});
    const [actionMessages, setActionMessages] = useState({});
    const [reportFlags, setReportFlags] = useState(getSavedReportFlags);

    // Initial API loading is handled directly by this effect.
    useEffect(() => {
        let cancelled = false;

        async function loadDashboard() {
            const resourceRequest = fetch(
                `${API_BASE_URL}/resources?skip=0&limit=100`
            )
                .then(async (response) => {
                    if (!response.ok) {
                        throw new Error(
                            `Unable to load resources (${response.status}).`
                        );
                    }

                    const data = await response.json();

                    if (!Array.isArray(data)) {
                        throw new Error("Unexpected resource response from server.");
                    }

                    if (!cancelled) {
                        setResources(data);
                        setError("");
                    }
                })
                .catch((err) => {
                    console.error("Resource fetching error:", err);
                    if (!cancelled) setError(getApiError(err));
                })
                .finally(() => {
                    if (!cancelled) setLoading(false);
                });

            const bookingRequest = apiRequest("/bookings/me")
                .then((response) => {
                    if (!Array.isArray(response.data)) {
                        throw new Error("Unexpected booking response from server.");
                    }

                    if (!cancelled) {
                        setBookings(response.data);
                        setBookingError("");
                    }
                })
                .catch((err) => {
                    console.error("Booking fetching error:", err);
                    if (!cancelled) setBookingError(getApiError(err));
                })
                .finally(() => {
                    if (!cancelled) setBookingsLoading(false);
                });

            await Promise.all([resourceRequest, bookingRequest]);
        }

        void loadDashboard();

        return () => {
            cancelled = true;
        };
    }, []);

    const fetchResources = useCallback(async () => {
        try {
            const response = await fetch(
                `${API_BASE_URL}/resources?skip=0&limit=100`
            );

            if (!response.ok) {
                throw new Error(`Unable to load resources (${response.status}).`);
            }

            const data = await response.json();

            if (!Array.isArray(data)) {
                throw new Error("Unexpected resource response from server.");
            }

            setResources(data);
            setError("");
        } catch (err) {
            console.error("Resource fetching error:", err);
            setError(getApiError(err));
        } finally {
            setLoading(false);
        }
    }, []);

    const fetchBookings = useCallback(async () => {
        try {
            const response = await apiRequest("/bookings/me");

            if (!Array.isArray(response.data)) {
                throw new Error("Unexpected booking response from server.");
            }

            setBookings(response.data);
            setBookingError("");
        } catch (err) {
            console.error("Booking fetching error:", err);
            setBookingError(getApiError(err));
        } finally {
            setBookingsLoading(false);
        }
    }, []);

    useEffect(() => {
        function handleEscape(event) {
            if (event.key === "Escape") setIsNavOpen(false);
        }

        function handleOutsideClick(event) {
            if (
                isNavOpen &&
                navRef.current &&
                !navRef.current.contains(event.target) &&
                !event.target.closest(".ob-menu-btn")
            ) {
                setIsNavOpen(false);
            }
        }

        document.addEventListener("keydown", handleEscape);
        document.addEventListener("mousedown", handleOutsideClick);

        return () => {
            document.removeEventListener("keydown", handleEscape);
            document.removeEventListener("mousedown", handleOutsideClick);
        };
    }, [isNavOpen]);

    function navigateSection(section) {
        setActiveNav(section);
        setIsNavOpen(false);

        if (section === "overview") {
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }

        document.getElementById(section)?.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }

    const firstName = user?.full_name?.trim()?.split(" ")[0] || "Student";

    const categories = [
        "All",
        ...new Set(resources.map((resource) => resource.category).filter(Boolean)),
    ];

    const filteredResources = resources.filter((resource) => {
        const searchText = search.toLowerCase();

        const matchesSearch =
            resource.title?.toLowerCase().includes(searchText) ||
            resource.location?.toLowerCase().includes(searchText) ||
            resource.category?.toLowerCase().includes(searchText);

        const matchesCategory =
            category === "All" || resource.category === category;

        return matchesSearch && matchesCategory;
    });

    const approvedBookings = bookings.filter(
        (booking) => booking.status?.toUpperCase() === "APPROVED"
    );

    const pendingBookings = bookings.filter(
        (booking) => booking.status?.toUpperCase() === "PENDING"
    );

    const rejectedBookings = bookings.filter(
        (booking) => booking.status?.toUpperCase() === "REJECTED"
    );

    const resourceMap = new Map(
        resources.map((resource) => [Number(resource.id), resource])
    );

    function handleLogout() {
        logout();
        navigate("/login", { replace: true });
    }

    function saveReportFlag(bookingId, reportType) {
        const updated = {
            ...reportFlags,
            [bookingId]: {
                ...reportFlags[bookingId],
                [reportType]: true,
            },
        };

        setReportFlags(updated);

        localStorage.setItem(
            "openbench_report_flags",
            JSON.stringify(updated)
        );
    }

    function setMessage(bookingId, message, type = "success") {
        setActionMessages((previous) => ({
            ...previous,
            [bookingId]: { message, type },
        }));
    }

    async function runBookingAction(bookingId, actionName, callback) {
        try {
            setActionLoading((previous) => ({
                ...previous,
                [bookingId]: actionName,
            }));

            setActionMessages((previous) => ({
                ...previous,
                [bookingId]: null,
            }));

            await callback();
            await fetchBookings();
        } catch (err) {
            console.error(`${actionName} error:`, err);
            setMessage(bookingId, getApiError(err), "error");
        } finally {
            setActionLoading((previous) => ({
                ...previous,
                [bookingId]: null,
            }));
        }
    }

    async function submitConditionReport(booking, reportType) {
        const isInitial = reportType === "initial";
        const reportLabel = isInitial ? "initial" : "final";

        const description = window.prompt(
            isInitial
                ? "Describe the resource's condition BEFORE using it:"
                : "Describe the resource's condition AFTER using it:"
        );

        if (description === null) return;

        if (description.trim().length < 5) {
            setMessage(
                booking.id,
                "Please enter at least 5 characters in the condition description.",
                "error"
            );
            return;
        }

        const evidence = window.prompt(
            "Enter an optional evidence reference (or leave blank):"
        );

        if (evidence === null) return;

        await runBookingAction(
            booking.id,
            `${reportLabel}-report`,
            async () => {
                await apiRequest(
                    `/bookings/${booking.id}/condition-reports/${reportLabel}`,
                    {
                        method: "POST",
                        body: JSON.stringify({
                            condition_description: description.trim(),
                            evidence_reference: evidence.trim() || null,
                        }),
                    }
                );

                saveReportFlag(booking.id, reportType);

                setMessage(
                    booking.id,
                    `${isInitial ? "Initial" : "Final"} condition report submitted successfully!`
                );
            }
        );
    }

    async function handleCheckIn(booking) {
        await runBookingAction(booking.id, "check-in", async () => {
            await apiRequest(`/bookings/${booking.id}/check-in`, {
                method: "POST",
            });

            setMessage(
                booking.id,
                "Check-in successful! Your booking is now active."
            );
        });
    }

    async function handleCheckOut(booking) {
        await runBookingAction(booking.id, "check-out", async () => {
            await apiRequest(`/bookings/${booking.id}/check-out`, {
                method: "POST",
            });

            setMessage(
                booking.id,
                "Check-out successful! The resource has been returned."
            );
        });
    }

    function renderBookingActions(booking) {
        const status = booking.status?.toUpperCase();
        const flags = reportFlags[booking.id] || {};
        const busy = actionLoading[booking.id];

        if (status === "PENDING") {
            return (
                <p className="booking-purpose">
                    Waiting for the resource owner to approve your request.
                </p>
            );
        }

        if (status === "REJECTED") return null;

        if (status === "APPROVED") {
            return (
                <div className="booking-lifecycle-actions">
                    {!flags.initial ? (
                        <button
                            className="resource-action"
                            disabled={!!busy}
                            onClick={() => submitConditionReport(booking, "initial")}
                        >
                            <ClipboardCheck size={16} />
                            {busy === "initial-report"
                                ? "Submitting..."
                                : "Initial Condition Report"}
                        </button>
                    ) : (
                        <p className="lifecycle-complete">
                            <ClipboardCheck size={16} />
                            Initial condition report submitted
                        </p>
                    )}

                    <button
                        className="resource-action"
                        disabled={!!busy || !flags.initial}
                        onClick={() => handleCheckIn(booking)}
                    >
                        <LogIn size={16} />
                        {busy === "check-in" ? "Checking in..." : "Check In"}
                    </button>

                    {!flags.initial && (
                        <p className="muted">
                            Submit your initial condition report before check-in.
                        </p>
                    )}
                </div>
            );
        }

        if (status === "IN_USE") {
            return (
                <div className="booking-lifecycle-actions">
                    {!flags.final ? (
                        <button
                            className="resource-action"
                            disabled={!!busy}
                            onClick={() => submitConditionReport(booking, "final")}
                        >
                            <ClipboardCheck size={16} />
                            {busy === "final-report"
                                ? "Submitting..."
                                : "Final Condition Report"}
                        </button>
                    ) : (
                        <p className="lifecycle-complete">
                            <ClipboardCheck size={16} />
                            Final condition report submitted
                        </p>
                    )}

                    <button
                        className="resource-action"
                        disabled={!!busy || !flags.final}
                        onClick={() => handleCheckOut(booking)}
                    >
                        <CheckOutIcon size={16} />
                        {busy === "check-out" ? "Checking out..." : "Check Out"}
                    </button>

                    {!flags.final && (
                        <p className="muted">
                            Submit your final condition report before check-out.
                        </p>
                    )}
                </div>
            );
        }

        if (status === "RETURNED") {
            return (
                <p className="lifecycle-complete">
                    <CheckOutIcon size={16} />
                    Booking completed. Resource returned successfully.
                </p>
            );
        }

        return null;
    }

    return (
        <div className="dashboard">
            <button
                className={`ob-menu-btn ${isNavOpen ? "is-open" : ""}`}
                onClick={() => setIsNavOpen((previous) => !previous)}
                aria-label={isNavOpen ? "Close navigation" : "Open navigation"}
                aria-expanded={isNavOpen}
                aria-controls="student-navigation"
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
                ref={navRef}
                id="student-navigation"
                className={`ob-sidebar ${isNavOpen ? "visible" : ""}`}
            >
                <Link
                    to="/student/dashboard"
                    className="ob-brand"
                    onClick={() => navigateSection("overview")}
                >
                    OpenBench.
                </Link>

                <p className="ob-menu-label">STUDENT MENU</p>

                <nav className="ob-links">
                    <button
                        className={`ob-item ${activeNav === "overview" ? "active" : ""}`}
                        onClick={() => navigateSection("overview")}
                    >
                        <LayoutDashboard size={19} />
                        Dashboard
                    </button>

                    <button
                        className={`ob-item ${activeNav === "resources" ? "active" : ""}`}
                        onClick={() => navigateSection("resources")}
                    >
                        <Package size={19} />
                        Explore Resources
                    </button>

                    <button
                        className={`ob-item ${activeNav === "bookings" ? "active" : ""}`}
                        onClick={() => navigateSection("bookings")}
                    >
                        <CalendarDays size={19} />
                        My Bookings
                    </button>
                </nav>

                <div className="ob-sidebar-bottom">
                    <div className="ob-profile">
                        <div className="ob-avatar">
                            {user?.full_name?.charAt(0)?.toUpperCase() || "S"}
                        </div>
                        <div>
                            <strong>{user?.full_name || "Student"}</strong>
                            <span>{user?.role || "STUDENT"} Account</span>
                        </div>
                    </div>

                    <button className="ob-logout" onClick={handleLogout}>
                        <LogOut size={18} />
                        Logout
                    </button>
                </div>
            </aside>

            <main className="dashboard-main" id="overview">
                <header className="dashboard-header">
                    <div>
                        <p className="eyebrow">STUDENT PORTAL</p>
                        <h1>Welcome back, {firstName}!</h1>
                        <p className="muted">
                            Discover resources. Share opportunities. Make more happen.
                        </p>
                    </div>
                </header>

                <section className="stats-grid">
                    <div className="stat-card">
                        <span>Available Resources</span>
                        <h2>{resources.length}</h2>
                        <p>Across your campus</p>
                    </div>
                    <div className="stat-card">
                        <span>My Bookings</span>
                        <h2>{bookingsLoading ? "..." : bookings.length}</h2>
                        <p>All your booking requests</p>
                    </div>
                    <div className="stat-card">
                        <span>Approved Bookings</span>
                        <h2>{bookingsLoading ? "..." : approvedBookings.length}</h2>
                        <p>Your approved requests</p>
                    </div>
                </section>

                <section className="resource-section" id="resources">
                    <div className="section-heading">
                        <div>
                            <p className="eyebrow">CAMPUS MARKETPLACE</p>
                            <h2>Explore Resources</h2>
                            <p className="muted">
                                Find equipment and spaces available on your campus.
                            </p>
                        </div>
                    </div>

                    <div className="resource-toolbar">
                        <div className="search-box">
                            <Search size={19} />
                            <input
                                type="text"
                                placeholder="Search resources or locations..."
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                            />
                        </div>

                        <select
                            value={category}
                            onChange={(event) => setCategory(event.target.value)}
                        >
                            {categories.map((item) => (
                                <option key={item} value={item}>
                                    {item === "All" ? "All Categories" : item}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="resource-grid">
                        {loading && (
                            <p className="empty-state">Loading campus resources...</p>
                        )}

                        {!loading && error && (
                            <div className="empty-state">
                                <p>{error}</p>
                                <button
                                    className="resource-action"
                                    onClick={() => {
                                        setLoading(true);
                                        setError("");
                                        fetchResources();
                                    }}
                                >
                                    <RefreshCw size={15} />
                                    Try Again
                                </button>
                            </div>
                        )}

                        {!loading &&
                            !error &&
                            filteredResources.map((resource) => {
                                const Icon = getResourceIcon(resource);

                                return (
                                    <article className="resource-card" key={resource.id}>
                                        <div className="resource-icon">
                                            <Icon size={28} />
                                        </div>

                                        <div className="resource-card-info">
                                            <span className="resource-category">
                                                {resource.category}
                                            </span>
                                            <h3>{resource.title}</h3>
                                            <p className="resource-location">
                                                <MapPin size={15} />
                                                {resource.location}
                                            </p>
                                        </div>

                                        <div className="resource-card-footer">
                                            <span className="availability available">
                                                Available
                                            </span>
                                            <button
                                                className="resource-action"
                                                onClick={() =>
                                                    navigate(`/resources/${resource.id}`)
                                                }
                                            >
                                                View Details
                                                <ArrowRight size={15} />
                                            </button>
                                        </div>
                                    </article>
                                );
                            })}

                        {!loading && !error && filteredResources.length === 0 && (
                            <p className="empty-state">
                                {resources.length === 0
                                    ? "No resources have been added to the marketplace yet."
                                    : "No resources found. Try another search."}
                            </p>
                        )}
                    </div>
                </section>

                <section className="booking-preview" id="bookings">
                    <div>
                        <p className="eyebrow">YOUR ACTIVITY</p>
                        <h2>My Bookings</h2>
                        <p className="muted">
                            Track your resource booking requests and their status.
                        </p>
                    </div>

                    {!bookingsLoading && !bookingError && (
                        <div className="booking-status-summary">
                            <span>Total: {bookings.length}</span>
                            <span>Pending: {pendingBookings.length}</span>
                            <span>Approved: {approvedBookings.length}</span>
                            <span>Rejected: {rejectedBookings.length}</span>
                        </div>
                    )}

                    {bookingsLoading && (
                        <div className="booking-placeholder">
                            <Clock size={22} />
                            <span>Loading your bookings...</span>
                        </div>
                    )}

                    {!bookingsLoading && bookingError && (
                        <div className="booking-placeholder">
                            <p>{bookingError}</p>
                            <button
                                className="resource-action"
                                onClick={() => {
                                    setBookingsLoading(true);
                                    setBookingError("");
                                    fetchBookings();
                                }}
                            >
                                <RefreshCw size={15} />
                                Try Again
                            </button>
                        </div>
                    )}

                    {!bookingsLoading && !bookingError && bookings.length === 0 && (
                        <div className="booking-placeholder">
                            <CalendarDays size={22} />
                            <span>You haven't made any bookings yet.</span>
                        </div>
                    )}

                    {!bookingsLoading && !bookingError && bookings.length > 0 && (
                        <div className="booking-list">
                            {bookings.map((booking) => {
                                const resource = resourceMap.get(
                                    Number(booking.resource_id)
                                );
                                const status = booking.status?.toUpperCase();

                                return (
                                    <article className="booking-item" key={booking.id}>
                                        <div className="booking-item-header">
                                            <div>
                                                <span className="booking-id">
                                                    Booking #{booking.id}
                                                </span>
                                                <h3>
                                                    {resource?.title ||
                                                        `Resource #${booking.resource_id}`}
                                                </h3>
                                            </div>
                                            <span
                                                className={`booking-status ${getStatusClass(status)}`}
                                            >
                                                {status || "UNKNOWN"}
                                            </span>
                                        </div>

                                        <p>
                                            <CalendarDays size={15} />
                                            Start: {formatDateTime(booking.start_at)}
                                        </p>
                                        <p>
                                            <Clock size={15} />
                                            End: {formatDateTime(booking.end_at)}
                                        </p>
                                        <p className="booking-purpose">
                                            <strong>Purpose:</strong> {booking.purpose}
                                        </p>

                                        {booking.reason && (
                                            <p className="booking-reason">
                                                <strong>Owner's note:</strong> {booking.reason}
                                            </p>
                                        )}

                                        {actionMessages[booking.id] && (
                                            <p
                                                className={
                                                    actionMessages[booking.id].type === "error"
                                                        ? "booking-reason"
                                                        : "lifecycle-complete"
                                                }
                                            >
                                                {actionMessages[booking.id].message}
                                            </p>
                                        )}

                                        {renderBookingActions(booking)}
                                    </article>
                                );
                            })}
                        </div>
                    )}

                    <button
                        className="resource-action"
                        onClick={() => {
                            setBookingsLoading(true);
                            setBookingError("");
                            fetchBookings();
                        }}
                        disabled={bookingsLoading}
                    >
                        <RefreshCw size={15} />
                        Refresh Bookings
                    </button>
                </section>

                <p className="demo-note">
                    Resources and student booking history are loaded from the
                    OpenBench backend.
                </p>
            </main>
        </div>
    );
}
