"""Read the latest ByteDeck release announcement back from GitHub Discussions.

The announce-changelog workflow (``.github/workflows/announce-changelog.yml``)
posts a Discussion titled ``Bytedeck App Updates (x.y.z[, ...])`` to the repo's
Announcements category whenever a new changelog version reaches production. This
module queries that Discussion so ``tenant.tasks.poll_release_announcement`` can
notify deck staff and link them to it.

Everything here is deliberately best-effort: any failure (no token configured, a
network or GitHub error, an unexpected response shape, or no matching discussion)
returns ``None`` so the poll simply does nothing that run rather than raising.
"""

import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
ANNOUNCEMENT_CATEGORY = "Announcements"

# The workflow's title, e.g. "Bytedeck App Updates (1.30.0 and 1.31.0)": match the
# fixed prefix, then pull every x.y.z version out of the parenthetical.
TITLE_RE = re.compile(r"^Bytedeck App Updates \(")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")

# Newest discussions first; 20 is ample headroom to find the latest announcement
# even when non-announcement discussions are interleaved.
_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 20, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { title url category { name } }
    }
  }
}
"""


def version_key(version):
    """Turn ``'1.30.0'`` into ``(1, 30, 0)`` so versions compare numerically."""
    return tuple(int(part) for part in version.split("."))


def get_latest_release_announcement():
    """Return ``(version, url)`` for the newest release announcement, or ``None``.

    ``version`` is the highest ``x.y.z`` named in the newest Announcements
    discussion whose title matches the changelog announcement format; ``url`` is
    that discussion's URL. Returns ``None`` whenever the feature can't act: no
    ``GITHUB_API_TOKEN``, a malformed ``RELEASE_ANNOUNCEMENT_REPO``, a network or
    GitHub error, an unexpected response, or no matching discussion.
    """
    token = settings.GITHUB_API_TOKEN
    if not token:
        return None
    try:
        owner, name = settings.RELEASE_ANNOUNCEMENT_REPO.split("/", 1)
    except ValueError:
        logger.warning(
            "RELEASE_ANNOUNCEMENT_REPO is not 'owner/name': %r", settings.RELEASE_ANNOUNCEMENT_REPO
        )
        return None

    try:
        response = requests.post(
            GITHUB_GRAPHQL_URL,
            json={"query": _QUERY, "variables": {"owner": owner, "name": name}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Release-announcement poll could not reach GitHub: %s", error)
        return None

    try:
        nodes = payload["data"]["repository"]["discussions"]["nodes"]
    except (KeyError, TypeError):
        logger.warning("Unexpected GitHub discussions response: %r", payload)
        return None

    # Nodes arrive newest-first, so the first announcement-shaped one is the latest.
    for node in nodes:
        node = node or {}
        title = node.get("title", "")
        category = (node.get("category") or {}).get("name", "")
        if category != ANNOUNCEMENT_CATEGORY or not TITLE_RE.match(title):
            continue
        versions = VERSION_RE.findall(title)
        if not versions:
            continue
        latest = max(versions, key=version_key)
        return latest, node.get("url", "")
    return None
