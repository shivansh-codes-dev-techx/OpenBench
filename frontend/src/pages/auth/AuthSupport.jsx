
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
    MailCheck,
    CheckCircle2,
    CircleAlert,
    KeyRound,
    ArrowLeft,
    RefreshCw,
    ShieldCheck,
} from "lucide-react";

import "../Auth.css";

function AuthShell({ icon: Icon, eyebrow, title, description, children }) {
    return (
        <main className="auth-support-page">
            <section className="auth-support-card">
                <Link to="/login" className="auth-support-brand">
                    OpenBench<span>.</span>
                </Link>

                <div className="auth-support-icon">
                    <Icon size={30} />
                </div>

                <span className="auth-support-eyebrow">{eyebrow}</span>
                <h1>{title}</h1>
                <p className="auth-support-description">{description}</p>

                {children}

                <div className="auth-support-footer">
                    <ShieldCheck size={15} />
                    <span>Secure campus resource sharing</span>
                </div>
            </section>
        </main>
    );
}

export function VerificationPending() {
    const [email, setEmail] = useState("");
    const [message, setMessage] = useState("");

    function handleResend(event) {
        event.preventDefault();
        setMessage(
            "UI preview only. Email verification will be connected after the backend API is finalized."
        );
    }

    return (
        <AuthShell
            icon={MailCheck}
            eyebrow="EMAIL VERIFICATION"
            title="Check your inbox"
            description="Your account needs email verification before you can access all OpenBench features."
        >
            <div className="auth-support-notice">
                <MailCheck size={19} />
                <p>
                    Open your verification email and follow the link to
                    confirm your email address.
                </p>
            </div>

            <form onSubmit={handleResend} className="auth-support-form">
                <label htmlFor="resend-email">
                    Didn't receive the email?
                </label>

                <input
                    id="resend-email"
                    type="email"
                    placeholder="Enter your registered email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                />

                <button type="submit" className="auth-support-primary">
                    <RefreshCw size={17} />
                    Resend verification email
                </button>
            </form>

            {message && (
                <p className="auth-support-message" role="status">
                    {message}
                </p>
            )}

            <Link to="/login" className="auth-support-back">
                <ArrowLeft size={16} />
                Back to sign in
            </Link>
        </AuthShell>
    );
}

export function VerifyEmail() {
    const [params] = useSearchParams();
    const status = params.get("status");

    if (status === "success") {
        return (
            <AuthShell
                icon={CheckCircle2}
                eyebrow="EMAIL VERIFIED"
                title="You're verified!"
                description="Your email verification status is confirmed in this UI preview."
            >
                <div className="auth-support-success">
                    <CheckCircle2 size={20} />
                    Email verification successful
                </div>

                <Link to="/login" className="auth-support-primary">
                    Continue to sign in
                </Link>
            </AuthShell>
        );
    }

    if (status === "failed" || status === "expired") {
        return (
            <AuthShell
                icon={CircleAlert}
                eyebrow="VERIFICATION ISSUE"
                title={
                    status === "expired"
                        ? "Link expired"
                        : "Verification unsuccessful"
                }
                description="This is a preview state. The actual verification result will be determined by the backend."
            >
                <div className="auth-support-warning">
                    <CircleAlert size={19} />
                    Your email verification could not be confirmed.
                </div>

                <Link
                    to="/verification-pending"
                    className="auth-support-primary"
                >
                    Request another verification email
                </Link>

                <Link to="/login" className="auth-support-back">
                    <ArrowLeft size={16} />
                    Back to sign in
                </Link>
            </AuthShell>
        );
    }

    return (
        <AuthShell
            icon={MailCheck}
            eyebrow="EMAIL VERIFICATION"
            title="Verify your email"
            description="The verification link will be processed here once the backend contract is connected."
        >
            <div className="auth-support-notice">
                <MailCheck size={19} />
                <p>Waiting for verification result.</p>
            </div>

            <Link
                to="/verification-pending"
                className="auth-support-primary"
            >
                View verification instructions
            </Link>
        </AuthShell>
    );
}

export function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [message, setMessage] = useState("");

    function handleSubmit(event) {
        event.preventDefault();

        setMessage(
            "UI preview only. Password reset email delivery will be connected after the backend API is finalized."
        );
    }

    return (
        <AuthShell
            icon={KeyRound}
            eyebrow="ACCOUNT RECOVERY"
            title="Forgot password?"
            description="Enter your registered email address to begin the password recovery process."
        >
            <form onSubmit={handleSubmit} className="auth-support-form">
                <label htmlFor="recovery-email">Email address</label>

                <input
                    id="recovery-email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                />

                <button type="submit" className="auth-support-primary">
                    Send reset instructions
                </button>
            </form>

            {message && (
                <p className="auth-support-message" role="status">
                    {message}
                </p>
            )}

            <Link to="/login" className="auth-support-back">
                <ArrowLeft size={16} />
                Back to sign in
            </Link>
        </AuthShell>
    );
}

export function ResetPassword() {
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [message, setMessage] = useState("");

    function handleSubmit(event) {
        event.preventDefault();

        if (password.length < 8) {
            setMessage("Password must contain at least 8 characters.");
            return;
        }

        if (password !== confirmPassword) {
            setMessage("Passwords do not match.");
            return;
        }

        setMessage(
            "UI preview only. Password reset will be connected after the backend API is finalized."
        );
    }

    return (
        <AuthShell
            icon={KeyRound}
            eyebrow="ACCOUNT RECOVERY"
            title="Create a new password"
            description="Choose a new password for your OpenBench account."
        >
            <form onSubmit={handleSubmit} className="auth-support-form">
                <label htmlFor="new-password">New password</label>

                <input
                    id="new-password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="At least 8 characters"
                    minLength={8}
                    required
                />

                <label htmlFor="confirm-password">
                    Confirm password
                </label>

                <input
                    id="confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(event) =>
                        setConfirmPassword(event.target.value)
                    }
                    placeholder="Enter password again"
                    required
                />

                <button type="submit" className="auth-support-primary">
                    Reset password
                </button>
            </form>

            {message && (
                <p className="auth-support-message" role="status">
                    {message}
                </p>
            )}

            <Link to="/login" className="auth-support-back">
                <ArrowLeft size={16} />
                Back to sign in
            </Link>
        </AuthShell>
    );
}
