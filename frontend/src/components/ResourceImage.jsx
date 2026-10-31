import { useState } from "react";

import { getResourceImageUrls } from "../utils/resourceImages";

export default function ResourceImage({
    resource,
    fallbackIcon,
    className = "",
    height = 190,
}) {
    const imageUrls = getResourceImageUrls(resource);
    const imageSignature = imageUrls.join("|");
    const [failedState, setFailedState] = useState({
        signature: "",
        urls: [],
    });
    const failedUrls =
        failedState.signature === imageSignature ? failedState.urls : [];
    const currentImage = imageUrls.find((url) => !failedUrls.includes(url));

    function handleImageError() {
        if (!currentImage) return;

        setFailedState((previous) => ({
            signature: imageSignature,
            urls:
                previous.signature === imageSignature
                    ? [...previous.urls, currentImage]
                    : [currentImage],
        }));
    }

    return (
        <div
            className={`resource-image ${className}`.trim()}
            style={{
                position: "relative",
                width: "100%",
                height: `${height}px`,
                overflow: "hidden",
                borderRadius: "12px",
                background: "#eef2f7",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
            }}
        >
            {currentImage ? (
                <img
                    key={currentImage}
                    src={currentImage}
                    alt={resource?.title || "Resource"}
                    loading="lazy"
                    decoding="async"
                    onError={handleImageError}
                    style={{
                        position: "absolute",
                        inset: 0,
                        display: "block",
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                    }}
                />
            ) : (
                <div
                    role="img"
                    aria-label="No image available"
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "9px",
                        color: "#64748b",
                    }}
                >
                    {fallbackIcon}
                    <span style={{ fontSize: "12px" }}>
                        No image available
                    </span>
                </div>
            )}

            {imageUrls.length > 1 && (
                <span
                    style={{
                        position: "absolute",
                        right: "10px",
                        bottom: "10px",
                        background: "rgba(15, 23, 42, 0.85)",
                        color: "#ffffff",
                        padding: "5px 9px",
                        borderRadius: "20px",
                        fontSize: "12px",
                        zIndex: 2,
                    }}
                >
                    {imageUrls.length} photos
                </span>
            )}
        </div>
    );
}
