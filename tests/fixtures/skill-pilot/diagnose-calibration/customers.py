CUSTOMERS = {"customer-42": {"name": "Ada"}}


def parse_identifier(value: str) -> str:
    return value.lower()


def lookup_customer(identifier: str) -> dict[str, str]:
    return CUSTOMERS[parse_identifier(identifier)]
