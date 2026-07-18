def get_timeout(raw: str | None) -> int:
    if raw is None:
        return 30
    return int(raw) or 30
