export function normalizeImageUrl(value, apiBaseUrl = import.meta.env.VITE_API_BASE_URL) {
    if (typeof value !== "string" || !value.trim()) {
        return "";
    }

    const path = value.trim();

    if (/^(https?:\/\/|data:|blob:)/i.test(path)) {
        return path;
    }

    const baseUrl =
        typeof apiBaseUrl === "string"
            ? apiBaseUrl.trim().replace(/\/+$/, "")
            : "";

    if (!baseUrl) {
        console.error(
            "Cannot resolve resource image URL: VITE_API_BASE_URL is not configured."
        );
        return "";
    }

    try {
        return new URL(path, `${baseUrl}/`).href;
    } catch (error) {
        console.error("Invalid resource image URL:", {
            value,
            apiBaseUrl: baseUrl,
            error,
        });

        return "";
    }
}

export function getResourceImageUrls(resource, apiBaseUrl) {
    if (!resource || typeof resource !== "object") {
        return [];
    }

    const imageValues = [];

    function addImage(value) {
        if (!value) return;

        if (typeof value === "string") {
            imageValues.push(value);
            return;
        }

        if (Array.isArray(value)) {
            value.forEach(addImage);
            return;
        }

        if (typeof value === "object") {
            const imagePath = [
                value.url,
                value.image_url,
                value.imageUrl,
                value.file_url,
                value.fileUrl,
                value.image_path,
                value.imagePath,
                value.file_path,
                value.filePath,
                value.path,
                value.src,
                value.href,
                value.download_url,
                value.downloadUrl,
            ].find((candidate) => typeof candidate === "string" && candidate.trim());

            if (imagePath) {
                addImage(imagePath);
            }
        }
    }

    addImage(resource.primary_image_url);
    addImage(resource.primaryImageUrl);
    addImage(resource.images);

    [
        resource.primary_image,
        resource.image_url,
        resource.imageUrl,
        resource.photo_url,
        resource.photoUrl,
        resource.thumbnail_url,
        resource.thumbnailUrl,
        resource.image,
        resource.image_urls,
        resource.imageUrls,
        resource.photos,
        resource.resource_images,
        resource.attachments,
    ].forEach(addImage);

    return [
        ...new Set(
            imageValues
                .map((value) => normalizeImageUrl(value, apiBaseUrl))
                .filter(Boolean)
        ),
    ];
}
