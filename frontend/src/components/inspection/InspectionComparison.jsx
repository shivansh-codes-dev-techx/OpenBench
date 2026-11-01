import { useEffect, useMemo } from "react";
import { CheckCircle2, ClipboardCheck, X } from "lucide-react";
import "./InspectionComparison.css";

const ANGLES = ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"];

function createImageUrls(inspection) {
    if (!inspection?.images) return {};

    return Object.fromEntries(
        ANGLES.map((angle) => {
            const file = inspection.images[angle];

            return [
                angle,
                file instanceof File ? URL.createObjectURL(file) : null,
            ];
        })
    );
}

function InspectionImage({ angle, initialUrl, finalUrl }) {
    return (
        <div className="comparison-angle">
            <h4>{angle}</h4>

            <div className="comparison-images">
                <div className="comparison-image-panel">
                    <span>Initial</span>
                    {initialUrl ? (
                        <img src={initialUrl} alt={`Initial ${angle} view`} />
                    ) : (
                        <div className="comparison-no-image">No image</div>
                    )}
                </div>

                <div className="comparison-image-panel">
                    <span>Final</span>
                    {finalUrl ? (
                        <img src={finalUrl} alt={`Final ${angle} view`} />
                    ) : (
                        <div className="comparison-no-image">No image</div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default function InspectionComparison({
    initialInspection,
    finalInspection,
    reviewed = false,
    onReviewed,
    onClose,
}) {
    const initialUrls = useMemo(
        () => createImageUrls(initialInspection),
        [initialInspection]
    );

    const finalUrls = useMemo(
        () => createImageUrls(finalInspection),
        [finalInspection]
    );

    useEffect(() => {
        return () => {
            Object.values(initialUrls).forEach((url) => {
                if (url) URL.revokeObjectURL(url);
            });

            Object.values(finalUrls).forEach((url) => {
                if (url) URL.revokeObjectURL(url);
            });
        };
    }, [initialUrls, finalUrls]);

    if (!initialInspection || !finalInspection) return null;

    return (
        <section className="inspection-comparison">
            <div className="comparison-header">
                <div>
                    <div className="comparison-heading">
                        <ClipboardCheck size={22} />
                        <h3>Inspection Comparison</h3>
                    </div>
                    <p>Compare the resource condition before and after the booking.</p>
                </div>

                <button
                    type="button"
                    className="comparison-close"
                    onClick={onClose}
                    aria-label="Close comparison"
                >
                    <X size={20} />
                </button>
            </div>

            <div className="comparison-legend">
                <span className="initial-label">Initial inspection</span>
                <span className="final-label">Final inspection</span>
            </div>

            <div className="comparison-grid">
                {ANGLES.map((angle) => (
                    <InspectionImage
                        key={angle}
                        angle={angle}
                        initialUrl={initialUrls[angle]}
                        finalUrl={finalUrls[angle]}
                    />
                ))}
            </div>

            <div className="comparison-descriptions">
                <div>
                    <h4>Initial condition</h4>
                    <p>
                        {initialInspection.description ||
                            "No initial condition description provided."}
                    </p>
                </div>

                <div>
                    <h4>Final condition</h4>
                    <p>
                        {finalInspection.description ||
                            "No final condition description provided."}
                    </p>
                </div>
            </div>

            <div className="comparison-review">
                <div>
                    <strong>
                        {reviewed ? "Inspection reviewed" : "Owner review required"}
                    </strong>
                    <p>
                        {reviewed
                            ? "You have marked this comparison as reviewed."
                            : "Review the images and descriptions before marking this comparison as reviewed."}
                    </p>
                </div>

                <button
                    type="button"
                    className="comparison-review-button"
                    onClick={onReviewed}
                    disabled={reviewed}
                >
                    <CheckCircle2 size={17} />
                    {reviewed ? "Reviewed" : "Mark as reviewed"}
                </button>
            </div>

            <p className="comparison-disclaimer">
                Demo mode: inspection images and review status are held in browser
                memory only. They are not uploaded to the backend or permanently saved.
            </p>
        </section>
    );
}
