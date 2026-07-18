def slugify(raw_slug: str | None) -> str:
    if raw_slug is None:
        return "untitled"
    return raw_slug.strip().lower().replace(" ", "-")
