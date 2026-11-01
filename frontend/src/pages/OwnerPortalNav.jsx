import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
    CalendarDays,
    LayoutDashboard,
    LogOut,
    Package,
} from "lucide-react";

import { useAuth } from "../context/useAuth";

const navigationItems = [
    {
        id: "dashboard",
        label: "Dashboard",
        to: "/owner/dashboard",
        Icon: LayoutDashboard,
    },
    {
        id: "resources",
        label: "My Resources",
        to: "/owner/resources",
        Icon: Package,
    },
    {
        id: "bookings",
        label: "Booking Requests",
        to: "/owner/dashboard#requests",
        Icon: CalendarDays,
    },
];

export default function OwnerPortalNav() {
    const { user, logout } = useAuth();
    const location = useLocation();
    const navigate = useNavigate();
    const [isOpen, setIsOpen] = useState(false);

    const activeItem =
        location.pathname === "/owner/resources"
            ? "resources"
            : location.hash === "#requests"
                ? "bookings"
                : "dashboard";

    useEffect(() => {
        function handleEscape(event) {
            if (event.key === "Escape") setIsOpen(false);
        }

        window.addEventListener("keydown", handleEscape);
        return () => window.removeEventListener("keydown", handleEscape);
    }, []);

    function handleLogout() {
        setIsOpen(false);
        logout();
        navigate("/login", { replace: true });
    }

    return (
        <>
            <button
                type="button"
                className={`ob-menu-btn ${isOpen ? "is-open" : ""}`}
                onClick={() => setIsOpen((open) => !open)}
                aria-label={isOpen ? "Close navigation" : "Open navigation"}
                aria-expanded={isOpen}
                aria-controls="owner-navigation"
            >
                <span />
                <span />
                <span />
            </button>

            <div
                className={`ob-nav-scrim ${isOpen ? "visible" : ""}`}
                onClick={() => setIsOpen(false)}
                aria-hidden="true"
            />

            <aside
                className={`ob-sidebar ${isOpen ? "visible" : ""}`}
                id="owner-navigation"
                aria-label="Owner navigation"
            >
                <div className="ob-brand">OpenBench.</div>
                <p className="ob-menu-label">OWNER PORTAL</p>

                <nav className="ob-links">
                    {navigationItems.map(({ id, label, to, Icon }) => (
                        <Link
                            key={id}
                            className={`ob-item ${activeItem === id ? "active" : ""}`}
                            to={to}
                            onClick={() => setIsOpen(false)}
                            aria-current={activeItem === id ? "page" : undefined}
                        >
                            <Icon size={19} />
                            {label}
                        </Link>
                    ))}
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
                        onClick={handleLogout}
                    >
                        <LogOut size={18} />
                        Logout
                    </button>
                </div>
            </aside>
        </>
    );
}
