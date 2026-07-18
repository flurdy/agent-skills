from html import escape


def render_user_badge(user: dict[str, object]) -> str:
    label = str(user["display_name"]).strip()
    return f'<span class="user-badge">{escape(label)}</span>'
