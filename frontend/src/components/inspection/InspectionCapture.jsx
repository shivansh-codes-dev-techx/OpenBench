
import { useEffect, useRef, useState } from "react";
import {
    Camera,
    CheckCircle2,
    ImagePlus,
    RotateCcw,
    Trash2,
    X,
} from "lucide-react";
import "./InspectionCapture.css";

const ANGLES = ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"];
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MIN_DESCRIPTION_LENGTH = 10;

const createEmptyImages = () =>
    Object.fromEntries(ANGLES.map((angle) => [angle, null]));

export default function InspectionCapture({
    reportType = "initial",
    onCancel,
    onComplete,
}) {
    const [images, setImages] = useState(createEmptyImages);
    const [imageUrls, setImageUrls] = useState({});
    const [description, setDescription] = useState("");
    const [errors, setErrors] = useState({});
    const [isSubmitting, setIsSubmitting] = useState(false);

    const inputRefs = useRef({});
    const imageUrlsRef = useRef({});

    const completedCount = ANGLES.filter(
        (angle) => Boolean(images[angle])
    ).length;

    const progress = (completedCount / ANGLES.length) * 100;

    useEffect(() => {
        return () => {
            Object.values(imageUrlsRef.current).forEach((url) => {
                if (url) {
                    URL.revokeObjectURL(url);
                }
            });
        };
    }, []);

    const handleFileChange = (angle, event) => {
        const file = event.target.files?.[0];

        // Allow selecting the same file again.
        event.target.value = "";

        if (!file) return;

        if (!file.type.startsWith("image/")) {
            setErrors((previous) => ({
                ...previous,
                [angle]: "Please select an image file.",
            }));
            return;
        }

        if (file.size > MAX_FILE_SIZE) {
            setErrors((previous) => ({
                ...previous,
                [angle]: "Image must be 10 MB or smaller.",
            }));
            return;
        }

        const previewUrl = URL.createObjectURL(file);
        const previousUrl = imageUrlsRef.current[angle];
        if (previousUrl) URL.revokeObjectURL(previousUrl);

        imageUrlsRef.current = {
            ...imageUrlsRef.current,
            [angle]: previewUrl,
        };

        setImages((previous) => ({
            ...previous,
            [angle]: file,
        }));

        setImageUrls((previous) => ({
            ...previous,
            [angle]: previewUrl,
        }));

        setErrors((previous) => ({
            ...previous,
            [angle]: "",
            form: "",
        }));
    };

    const removeImage = (angle) => {
        const previousUrl = imageUrlsRef.current[angle];
        if (previousUrl) URL.revokeObjectURL(previousUrl);

        const nextImageUrls = { ...imageUrlsRef.current };
        delete nextImageUrls[angle];
        imageUrlsRef.current = nextImageUrls;

        setImages((previous) => ({
            ...previous,
            [angle]: null,
        }));

        setImageUrls((previous) => ({
            ...previous,
            [angle]: null,
        }));

        setErrors((previous) => ({
            ...previous,
            [angle]: "",
            form: "",
        }));
    };

    const resetInspection = () => {
        Object.values(imageUrlsRef.current).forEach((url) => {
            if (url) URL.revokeObjectURL(url);
        });
        imageUrlsRef.current = {};

        setImages(createEmptyImages());
        setImageUrls({});
        setDescription("");
        setErrors({});

        Object.values(inputRefs.current).forEach((input) => {
            if (input) {
                input.value = "";
            }
        });
    };

    const handleSubmit = () => {
        const missingAngles = ANGLES.filter(
            (angle) => !images[angle]
        );

        if (missingAngles.length > 0) {
            setErrors((previous) => ({
                ...previous,
                form:
                    "Please add photos for: " +
                    missingAngles.join(", ") +
                    ".",
            }));
            return;
        }

        if (description.trim().length < MIN_DESCRIPTION_LENGTH) {
            setErrors((previous) => ({
                ...previous,
                form:
                    "Please enter at least " +
                    MIN_DESCRIPTION_LENGTH +
                    " characters describing the condition.",
            }));
            return;
        }

        setIsSubmitting(true);

        try {
            onComplete?.({
                reportType,
                description: description.trim(),
                images: { ...images },
            });
        } catch (error) {
            console.error("Inspection completion failed:", error);

            setErrors((previous) => ({
                ...previous,
                form: "Unable to complete the inspection. Please try again.",
            }));
        } finally {
            setIsSubmitting(false);
        }
    };

    const title =
        reportType === "final"
            ? "Final Inspection"
            : "Initial Inspection";

    return (
        <section className="inspection-capture">
            <header className="inspection-header">
                <div>
                    <p className="inspection-eyebrow">
                        SIX-ANGLE CONDITION RECORD
                    </p>

                    <h2>{title}</h2>

                    <p className="inspection-description">
                        Photograph the resource from all six angles and
                        describe its current condition.
                    </p>
                </div>

                <button
                    type="button"
                    className="inspection-close"
                    onClick={onCancel}
                    aria-label="Close inspection"
                    disabled={isSubmitting}
                >
                    <X size={19} />
                </button>
            </header>

            <div className="inspection-progress-heading">
                <span>Photo completion</span>
                <strong>{completedCount} of 6 angles</strong>
            </div>

            <div
                className="inspection-progress-track"
                role="progressbar"
                aria-label="Inspection photo completion"
                aria-valuenow={completedCount}
                aria-valuemin={0}
                aria-valuemax={6}
            >
                <div
                    className="inspection-progress-fill"
                    style={{ width: `${progress}%` }}
                />
            </div>

            <div className="inspection-angle-grid">
                {ANGLES.map((angle) => (
                    <article
                        className="inspection-angle-card"
                        key={angle}
                    >
                        <div className="inspection-angle-label">
                            <span>{angle} VIEW</span>

                            {images[angle] && (
                                <CheckCircle2
                                    className="inspection-angle-check"
                                    size={17}
                                />
                            )}
                        </div>

                        <div className="inspection-image-preview">
                            {imageUrls[angle] ? (
                                <img
                                    src={imageUrls[angle]}
                                    alt={`${angle} view of resource`}
                                />
                            ) : (
                                <div className="inspection-empty-preview">
                                    <Camera size={25} />
                                    <span>No photo selected</span>
                                </div>
                            )}
                        </div>

                        <input
                            ref={(element) => {
                                inputRefs.current[angle] = element;
                            }}
                            className="inspection-file-input"
                            type="file"
                            accept="image/*"
                            capture="environment"
                            onChange={(event) =>
                                handleFileChange(angle, event)
                            }
                            disabled={isSubmitting}
                        />

                        <div className="inspection-image-actions">
                            <button
                                type="button"
                                className="inspection-select-button"
                                onClick={() =>
                                    inputRefs.current[angle]?.click()
                                }
                                disabled={isSubmitting}
                            >
                                {images[angle] ? (
                                    <>
                                        <RotateCcw size={14} />
                                        Retake
                                    </>
                                ) : (
                                    <>
                                        <ImagePlus size={14} />
                                        Add photo
                                    </>
                                )}
                            </button>

                            {images[angle] && (
                                <button
                                    type="button"
                                    className="inspection-remove-button"
                                    onClick={() => removeImage(angle)}
                                    disabled={isSubmitting}
                                    aria-label={`Remove ${angle} photo`}
                                >
                                    <Trash2 size={14} />
                                </button>
                            )}
                        </div>

                        {errors[angle] && (
                            <p className="inspection-error" role="alert">
                                {errors[angle]}
                            </p>
                        )}
                    </article>
                ))}
            </div>

            {/* A div is intentional here to avoid nested form submission. */}
            <div className="inspection-form">
                <label htmlFor={`inspection-description-${reportType}`}>
                    Condition description
                </label>

                <textarea
                    id={`inspection-description-${reportType}`}
                    value={description}
                    onChange={(event) => {
                        setDescription(event.target.value);

                        setErrors((previous) => ({
                            ...previous,
                            form: "",
                        }));
                    }}
                    placeholder="Describe scratches, dents, missing parts, existing damage, or the overall condition..."
                    maxLength={1000}
                    disabled={isSubmitting}
                />

                <span className="inspection-character-count">
                    {description.length}/1000 characters
                </span>

                <p className="inspection-hint">
                    Include any visible damage or unusual condition details.
                </p>

                {errors.form && (
                    <p className="inspection-error" role="alert">
                        {errors.form}
                    </p>
                )}

                <div className="inspection-demo-notice">
                    <Camera size={17} />

                    <span>
                        Demo mode: photos are kept in browser memory.
                        They aren't uploaded or permanently stored.
                    </span>
                </div>

                <div className="inspection-footer">
                    <button
                        type="button"
                        className="inspection-submit-button"
                        onClick={handleSubmit}
                        disabled={isSubmitting}
                    >
                        <CheckCircle2 size={17} />

                        Complete{" "}
                        {reportType === "final" ? "Final" : "Initial"}{" "}
                        Inspection
                    </button>

                    <button
                        type="button"
                        className="inspection-reset-button"
                        onClick={resetInspection}
                        disabled={isSubmitting}
                    >
                        <RotateCcw size={15} />
                        Reset photos
                    </button>
                </div>
            </div>
        </section>
    );
}
