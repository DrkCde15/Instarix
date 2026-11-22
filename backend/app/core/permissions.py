"""RBAC por papel (usuários) e escopos (API keys)."""

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"*"}),
    "admin": frozenset(
        {
            "accounts:read",
            "accounts:write",
            "accounts:2fa",
            "jobs:read",
            "jobs:write",
            "keys:manage",
            "webhooks:read",
            "webhooks:write",
            "audit:read",
        }
    ),
    "operator": frozenset(
        {"accounts:read", "accounts:2fa", "jobs:read", "jobs:write"}
    ),
    "viewer": frozenset({"accounts:read", "jobs:read"}),
}

ALLOWED_SCOPES: frozenset[str] = frozenset(
    {
        "accounts:read",
        "accounts:write",
        "accounts:2fa",
        "jobs:read",
        "jobs:write",
        "keys:manage",
        "webhooks:read",
        "webhooks:write",
        "audit:read",
    }
)

ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS)


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def validate_scopes(scopes: list[str]) -> list[str]:
    unknown = sorted(set(scopes) - ALLOWED_SCOPES)
    if unknown:
        raise ValueError(f"Escopos desconhecidos: {', '.join(unknown)}")
    return sorted(set(scopes))
