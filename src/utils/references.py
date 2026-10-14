"""Parse URLs and DOIs and resolve DOI targets without fetching landing pages.

``parse_url`` splits a URL into its parts, ``extract_doi`` extracts the identifier,
and ``resolve_doi`` asks the DOI service which URL the identifier points to.
"""

import re
from urllib.error import HTTPError
from urllib.parse import SplitResult, quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


USER_AGENT = "search-readiness-evaluator/0.1"
DOI_HOSTS = {"doi.org", "dx.doi.org"}
_DOI_PATTERN = re.compile(r"(?:doi:\s*)?(10\.[0-9]{4,9}/\S+)", re.IGNORECASE)


def parse_url(reference: str) -> SplitResult | None:
    """Split an HTTP(S) URL into its parts if it meets the accepted URL rules.

    Args:
        reference: A URL string. Leading and trailing whitespace is removed.
            If the scheme is missing, ``https://`` is added only for addresses
            starting with one of these domains followed by a slash:
            zenodo.org, www.zenodo.org, datadryad.org,
            www.datadryad.org, figshare.com, www.figshare.com, api.figshare.com,
            rcsb.org, www.rcsb.org, data.rcsb.org, wwpdb.org, www.wwpdb.org,
            doi.org, or dx.doi.org. Other domains require an explicit scheme.

    Returns:
        A SplitResult exposing URL parts such as ``scheme``, ``hostname``,
        ``path``, ``query``, and ``fragment``. Returns None if parsing fails
        or the URL violates any of these rules: the scheme must be http/https,
        a hostname must be present, credentials and internal whitespace are
        forbidden, and the port must be omitted or use the standard value
        (80 for HTTP, 443 for HTTPS).

    This function makes no network requests. It does not check whether the
    address is reachable or supported by a repository adapter; HTTP(S) URLs
    on other domains are also accepted.

    Examples:
        >>> url = parse_url("  zenodo.org/records/123  ")
        >>> (url.scheme, url.hostname, url.path)
        ('https', 'zenodo.org', '/records/123')
        >>> url = parse_url("https://example.org/item?version=2#files")
        >>> (url.query, url.fragment)
        ('version=2', 'files')
        >>> parse_url("example.org/item") is None
        True
        >>> parse_url("https://user:password@zenodo.org/records/123") is None
        True
        >>> parse_url("https://zenodo.org:8443/records/123") is None
        True
    """
    reference = reference.strip()
    # Add https:// scheme if missing and applicable
    if reference.lower().startswith(
        (
            "zenodo.org/", "www.zenodo.org/",
            "datadryad.org/", "www.datadryad.org/",
            "figshare.com/", "www.figshare.com/", "api.figshare.com/",
            "rcsb.org/", "www.rcsb.org/", "data.rcsb.org/",
            "wwpdb.org/", "www.wwpdb.org/",
            "doi.org/", "dx.doi.org/",
        )
    ):
        reference = f"https://{reference}"

    try:
        url = urlsplit(reference)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.port not in {None, 80 if url.scheme == "http" else 443}
            or any(char.isspace() for char in reference)
        ):
            return None
    except ValueError:
        return None
    return url


def extract_doi(reference: str) -> str | None:
    """Extract a bare DOI from an identifier, a ``doi:`` reference, or a DOI URL.

    Args:
        reference: A bare DOI such as ``10.5281/zenodo.123``, the same DOI
            with a ``doi:`` prefix, or a URL on doi.org or dx.doi.org.
            Leading and trailing whitespace is removed. For DOI URLs, the
            path is used, escapes such as ``%2F`` are decoded, and the query
            string and fragment are ignored.

    Returns:
        A DOI string without the ``doi:`` prefix or resolver address.
        Letter case in the DOI is preserved. Returns None if the whole input
        does not match a supported form; DOIs embedded in sentences or URLs
        on other domains are not extracted. The accepted identifier format
        is ``10.``, 4 to 9 digits, a slash, and a nonempty suffix containing
        no whitespace.

    This is a format check only. The function makes no network requests and
    does not verify whether the DOI exists or which repository it points to.

    Examples:
        >>> extract_doi("10.5281/zenodo.123")
        '10.5281/zenodo.123'
        >>> extract_doi("  DOI: 10.1234/AbC  ")
        '10.1234/AbC'
        >>> extract_doi("doi.org/10.5281%2Fzenodo.123?source=test#details")
        '10.5281/zenodo.123'
        >>> extract_doi("https://example.org/10.5281/zenodo.123") is None
        True
        >>> extract_doi("See DOI 10.5281/zenodo.123") is None
        True
        >>> extract_doi("10.12/example") is None
        True
    """
    candidate = reference.strip()
    url = parse_url(candidate)
    if url is not None:
        if url.hostname not in DOI_HOSTS:
            return None
        candidate = unquote(url.path.removeprefix("/"))

    match = _DOI_PATTERN.fullmatch(candidate)
    return match.group(1) if match else None


class _NoRedirects(HTTPRedirectHandler):
    """Expose redirects for manual handling instead of fetching their targets.

    Used by ``resolve_doi`` to inspect the domain in the Location header before
    making another request. Redirect responses are surfaced as HTTPError.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Decline to create a request for the redirect target.

        Args:
            req: The original HTTP request, supplied by urllib.
            fp: The open server response, whose body can be read.
            code: The HTTP redirect status code, such as 302.
            msg: The HTTP status message, such as "Found".
            headers: The response headers, including Location.
            newurl: The proposed redirect target URL.

        Returns:
            Always None, so urllib does not create another request
            automatically. These parameters belong to the HTTPRedirectHandler
            interface and are unused here. When this handler is installed in
            an opener, ``resolve_doi`` handles the response as an HTTPError.

        Example (no network request is made):
            >>> handler = _NoRedirects()
            >>> request = Request("https://doi.org/10.5281/zenodo.123")
            >>> target = "https://zenodo.org/records/123"
            >>> handler.redirect_request(
            ...     request, None, 302, "Found", {"Location": target}, target
            ... ) is None
            True
        """
        return None


def resolve_doi(doi: str) -> str:
    """Find a DOI's target URL through redirects without fetching its landing page.

    Args:
        doi: A bare identifier such as ``10.5281/zenodo.123``. This should
            already be the output of ``extract_doi``; its format is not
            checked here.

    Behavior:
        Sends a GET request to ``https://doi.org/{doi}`` with the DOI encoded
        for use in a URL. Makes at most 5 requests, each with a 30-second
        timeout. Follows redirects with status 301, 302, 303, 307, or 308 only
        within doi.org and dx.doi.org. Relative Location values are resolved
        against the current request URL.

    Returns:
        The first target URL outside the DOI resolvers, or a target rejected
        by ``parse_url``. The URL is returned as a string without fetching it.
        The caller must check whether the URL is acceptable and whether its
        repository is supported by an adapter.

    Raises:
        ValueError: No target outside the resolvers was returned within
            5 requests, or the resolver returned a successful response
            without redirecting to a record.
        HTTPError: The server returned an error such as HTTP 404, or a
            redirect lacks a supported status code or a nonempty Location
            header.
        URLError / TimeoutError: Network failures and timeouts are passed
            through to the caller.

    Example with an illustrative server response:
        If doi.org returns HTTP 302 for the DOI below with the header
        ``Location: https://zenodo.org/records/123``, the result is:

        >>> resolve_doi("10.5281/zenodo.123")  # doctest: +SKIP
        'https://zenodo.org/records/123'

        The returned URL is not fetched. This example is skipped by doctest
        because the actual response depends on the DOI service and whether
        the record exists. If Location contained only ``/10.5281/zenodo.456``,
        the function would continue with a request to
        ``https://doi.org/10.5281/zenodo.456``.
    """
    url = f"https://doi.org/{quote(doi, safe='/')}"
    opener = build_opener(_NoRedirects())

    for _ in range(5):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=30):
                break
        except HTTPError as error:
            location = error.headers.get("Location")
            if error.code not in {301, 302, 303, 307, 308} or not location:
                raise
            error.close()
            url = urljoin(url, location)
            target = parse_url(url)
            if target is None or target.hostname not in DOI_HOSTS:
                return url

    raise ValueError("The DOI resolver did not return a record URL.")
