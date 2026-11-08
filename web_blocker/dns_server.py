"""A minimal local DNS resolver: NXDOMAINs configured domains (and any of
their subdomains), forwards everything else upstream.

This replaces hosts-file blocking so the blocklist can scale to hundreds of
thousands of entries without the Windows hosts-file performance problems
that come with a file that large.
"""
import socket
import socketserver
import threading

import dns.message
import dns.rcode
import dns.rdatatype
import dns.rdataclass
import dns.rrset

UPSTREAM_DNS = ("1.1.1.3", 53)  # Cloudflare Family (malware + ADULT CONTENT) — 1.1.1.2 is malware-only, do not use
UPSTREAM_TIMEOUT = 3.0
DNS_PORT = 53


class BlocklistStore:
    """Thread-safe holder for the current blocked-domain set."""

    def __init__(self):
        self.blocked = frozenset()

    def set_domains(self, domains):
        self.blocked = frozenset(domains)  # reference swap is atomic under the GIL

    def is_blocked(self, qname):
        name = qname.rstrip(".").lower()
        labels = name.split(".")
        for i in range(len(labels) - 1):
            if ".".join(labels[i:]) in self.blocked:
                return True
        return False


def _forward(query_bytes):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(UPSTREAM_TIMEOUT)
        s.sendto(query_bytes, UPSTREAM_DNS)
        data, _ = s.recvfrom(65535)
        return data


def make_handler(store: BlocklistStore):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            data, sock = self.request
            try:
                query = dns.message.from_wire(data)
                qname = str(query.question[0].name) if query.question else ""

                # Special case: localhost always resolves to 127.0.0.1 / ::1
                if qname and qname.rstrip(".").lower() == "localhost":
                    response = dns.message.make_response(query)
                    if query.question[0].rdtype == dns.rdatatype.A:
                        response.answer.append(
                            dns.rrset.from_text("localhost.", 300, dns.rdataclass.IN, dns.rdatatype.A, "127.0.0.1")
                        )
                    elif query.question[0].rdtype == dns.rdatatype.AAAA:
                        response.answer.append(
                            dns.rrset.from_text("localhost.", 300, dns.rdataclass.IN, dns.rdatatype.AAAA, "::1")
                        )
                    sock.sendto(response.to_wire(), self.client_address)
                    return

                if qname and store.is_blocked(qname):
                    response = dns.message.make_response(query)
                    response.set_rcode(dns.rcode.NXDOMAIN)
                    sock.sendto(response.to_wire(), self.client_address)
                    return

                reply = _forward(data)
                sock.sendto(reply, self.client_address)
            except Exception:
                pass  # malformed packet or upstream timeout: drop, client will retry

    return Handler


class ThreadingUDPServerV4(socketserver.ThreadingUDPServer):
    address_family = socket.AF_INET
    allow_reuse_address = True
    daemon_threads = True


class ThreadingUDPServerV6(socketserver.ThreadingUDPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True
    daemon_threads = True


def start_servers(store: BlocklistStore, log=None):
    """Binds on 127.0.0.1:53 and ::1:53. Returns the list of servers that started."""
    handler = make_handler(store)
    servers = []

    for server_cls, host in ((ThreadingUDPServerV4, "127.0.0.1"), (ThreadingUDPServerV6, "::1")):
        try:
            server = server_cls((host, DNS_PORT), handler)
        except OSError as e:
            if log:
                log(f"Could not bind DNS server on {host}:{DNS_PORT} ({e}) — is something else using port 53?")
            continue
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)

    return servers
