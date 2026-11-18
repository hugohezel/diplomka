"""Bounded public HTTP transport for shared registry and target lookups."""

import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .references import USER_AGENT, parse_url


def _require_public_url(url):
    parsed = parse_url(url)
    if parsed is None or any(ord(c) < 32 for c in url):
        raise ValueError("Invalid public HTTP(S) destination.")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError("Lookup destination is not a public address.")


class _PublicRedirects(HTTPRedirectHandler):
    def __init__(self, deadline, limit):
        super().__init__()
        self.deadline, self.limit, self.chain = deadline, limit, []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if len(self.chain) >= self.limit or time.monotonic() >= self.deadline:
            raise ValueError("Lookup redirect/time limit exceeded.")
        _require_public_url(newurl)
        self.chain.append({'from': req.full_url, 'status': code, 'to': newurl})
        req.timeout = max(0.01, self.deadline - time.monotonic())
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _request(url, profile, *, method='GET', registry=False):
    deadline = time.monotonic() + profile['timeout']
    evidence = {'sourceUrl': url, 'method': method, 'checkedAt': datetime.now(timezone.utc).isoformat()}
    redirects = _PublicRedirects(deadline, profile['maxRedirects'])
    try:
        _require_public_url(url)
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json' if registry else '*/*'}
        if method == 'GET' and not registry:
            headers['Range'] = f"bytes=0-{profile['maxTargetBytes'] - 1}"
        request = Request(url, headers=headers, method=method)
        with build_opener(redirects).open(request, timeout=max(0.01, deadline - time.monotonic())) as response:
            evidence.update(targetUrl=response.geturl(), httpStatus=response.status,
                            contentType=response.headers.get('Content-Type', ''), redirectChain=redirects.chain)
            limit = profile['maxRegistryBytes'] if registry else profile['maxTargetBytes']
            body = response.read(limit + (1 if registry else 0)) if method != 'HEAD' else b''
            if time.monotonic() > deadline:
                raise ValueError('Lookup time limit exceeded.')
            if registry and len(body) > limit:
                raise ValueError('Registry response exceeded the size limit.')
            return {'status': 'PASS', 'message': 'Successful HTTP response.', 'body': body, **evidence}
    except HTTPError as error:
        evidence.update(httpStatus=error.code, targetUrl=error.geturl(), redirectChain=redirects.chain)
        error.close()
        return {'status': 'FAIL' if error.code in {404, 410} else 'UNSURE',
                'message': f'HTTP {error.code}.', **evidence}
    except (URLError, OSError, HTTPException, ValueError) as error:
        return {'status': 'UNSURE', 'message': f'Lookup unavailable: {error}', 'redirectChain': redirects.chain, **evidence}


def request_public_json(url, profile):
    result = _request(url, profile, registry=True)
    body = result.pop('body', None)
    if result['status'] == 'PASS':
        try:
            result['data'] = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            result.update(status='UNSURE', message='The registry did not return valid JSON.')
    return result


def _specific_destination(result):
    target = parse_url(result.get('targetUrl', ''))
    if not target or target.hostname in {'doi.org', 'dx.doi.org', 'hdl.handle.net', 'n2t.net'}:
        return False
    path = target.path.rstrip('/').casefold()
    return bool(path) and not re.search(r'/(?:login|signin|404|error|not-found|search|browse|home|en|index(?:\.html?)?)$', path)


def resolve_public_target(url, profile):
    head = _request(url, profile, method='HEAD')
    head.pop('body', None)
    content_type = head.get('contentType', '').split(';', 1)[0].lower()
    if head['status'] == 'PASS' and _specific_destination(head) and content_type and content_type not in {'text/html', 'application/xhtml+xml'}:
        return {**head, 'message': 'Target-specific resource reached by HEAD.', 'requests': [{k:v for k,v in head.items() if k != 'body'}]}
    get = _request(url, profile)
    body = get.pop('body', b'').decode('utf-8', errors='replace')
    get['requests'] = [{k:v for k,v in head.items() if k != 'body'}, {k:v for k,v in get.items() if k != 'requests'}]
    if get['status'] != 'PASS':
        return get
    title_match = re.search(r'<title[^>]*>(.*?)</title>', body, re.I | re.S)
    title = re.sub(r'\s+', ' ', title_match.group(1)).strip() if title_match else ''
    challenge = re.search(r'not found|404|access denied|just a moment|sign in|log in|verify.{0,15}human', title, re.I)
    if not _specific_destination(get) or challenge:
        get.update(status='UNSURE', message='A generic, challenge or unverified destination is not target-specific success.')
    else:
        get['message'] = 'Target-specific landing page, registry entry or resource reached.'
    get['pageTitle'] = title
    return get
