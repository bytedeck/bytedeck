from urllib.parse import urlsplit

from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_local_url(request, url):
    """Return `url` if it may be trusted as somewhere to send the user on this site.

    Args:
        request: the request being answered.
        url (str | None): a url from the request, such as a form's `next` or the Referer header.

    Returns:
        str | None: `url` when it stays on this host and keeps https for a request that came in
        over https, and is a path from the site's root or a full url; None otherwise, including
        for no url at all. Another host would make the view that redirects to it an open
        redirect. A path-relative url, such as "?tab=flagged" or "flagged/", is resolved
        against the url the browser is on when it follows the redirect, which is the action's
        own rather than the page the action came from.
    """
    if not url or not url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return None
    parts = urlsplit(url)
    if not parts.netloc and not parts.path.startswith('/'):
        return None
    return url


def where_from(request, avoid=()):
    """Return the page an action was taken from, if it may be trusted and is somewhere to go back to.

    That is the request's `next` (posted, then in the query string), which a page names when the
    action passes through a page of its own first, such as a confirmation; otherwise the page the
    browser sent the request from (the Referer header). Tabbed lists such as Quest Approvals and
    Quests give each tab its own url, so the page an action came from is the tab it was taken on,
    even when the button sat in a part of the page loaded afterwards (#2859).

    Args:
        request: the request being answered.
        avoid (iterable[str]): paths not to go back to, such as the page of something the action
            has just deleted.

    Returns:
        str | None: the url, or None when the request names nowhere that may be trusted.
    """
    for candidate in (request.POST.get('next'), request.GET.get('next'), request.META.get('HTTP_REFERER')):
        url = safe_local_url(request, candidate)
        if url and urlsplit(url).path not in avoid:
            return url
    return None


def redirect_back(request, fallback, *args, avoid=()):
    """Send the user back to the page an action was taken from, or to `fallback` (#2859).

    So a teacher who unflags a submission on the Flagged tab is still on the Flagged tab, rather
    than on the page's first tab.

    Args:
        request: the request being answered.
        fallback: where to go when the request names nowhere to go back to, as for
            ``django.shortcuts.redirect``.
        *args: arguments for `fallback`, as for ``django.shortcuts.redirect``.
        avoid (iterable[str]): paths not to go back to (see ``where_from``).

    Returns:
        HttpResponseRedirect: to the page the action was taken from, or to `fallback`.
    """
    url = where_from(request, avoid)
    if url:
        return redirect(url)
    return redirect(fallback, *args)
