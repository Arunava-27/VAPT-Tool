"""
Safety guardrails — validate agent actions before execution.
Prevents accidental scanning of public infrastructure or executing
dangerous commands without explicit authorisation.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

# RFC 1918 / loopback / link-local ranges — always permitted
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

# Well-known public test targets (explicitly allowed)
_ALLOWED_PUBLIC_TARGETS = {
    "scanme.nmap.org",
    "testphp.vulnweb.com",
    "demo.testfire.net",
    "juice-shop.herokuapp.com",
}

# Dangerous command patterns the exploitation agent must NOT execute blindly
_DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"dd\s+if=",
    r"mkfs\.",
    r":(){ :|:& };:",   # fork bomb
    r">\s*/dev/sd",
    r"shutdown",
    r"reboot",
    r"halt",
]


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str
    risk_level: str = "none"   # none | low | medium | high | critical


class GuardrailEngine:
    """
    Validates targets and agent-proposed actions before execution.
    All checks are bypassed if GUARDRAILS_ENABLED=false (not recommended).
    """

    def validate_target(self, target: str) -> GuardrailResult:
        if not settings.GUARDRAILS_ENABLED:
            return GuardrailResult(allowed=True, reason="Guardrails disabled")

        # Explicit block list from config
        if target in settings.BLOCKED_TARGETS:
            return GuardrailResult(
                allowed=False, reason=f"Target '{target}' is on the block list",
                risk_level="critical"
            )

        # Check against well-known test targets
        if target.lower() in _ALLOWED_PUBLIC_TARGETS:
            return GuardrailResult(
                allowed=True, reason="Known safe test target", risk_level="low"
            )

        # Try IP-based check
        try:
            ip = ipaddress.ip_address(target.split("/")[0])
            for private_range in _PRIVATE_RANGES:
                if ip in private_range:
                    return GuardrailResult(
                        allowed=True, reason="Private/internal IP range", risk_level="low"
                    )
            # Public IP — warn but allow (user is responsible)
            logger.warning(f"[Guardrail] Public IP target: {target}")
            return GuardrailResult(
                allowed=True,
                reason="Public IP — ensure you have written authorisation",
                risk_level="high"
            )
        except ValueError:
            pass  # Not an IP, treat as hostname

        # Hostname — allow but flag public-looking ones
        private_tlds = {".local", ".internal", ".corp", ".home", ".lan", ".intranet", ".private"}
        if any(target.lower().endswith(tld) for tld in private_tlds):
            return GuardrailResult(allowed=True, reason="Private hostname", risk_level="low")

        return GuardrailResult(
            allowed=True,
            reason="External hostname — ensure you have written authorisation",
            risk_level="medium"
        )

    def validate_command(self, command: str) -> GuardrailResult:
        if not settings.GUARDRAILS_ENABLED:
            return GuardrailResult(allowed=True, reason="Guardrails disabled")

        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return GuardrailResult(
                    allowed=False,
                    reason=f"Command matches dangerous pattern: {pattern}",
                    risk_level="critical"
                )
        return GuardrailResult(allowed=True, reason="Command passed guardrails")

    def validate_scan_scope(
        self, targets: List[str], requested_tools: List[str]
    ) -> Tuple[bool, List[str]]:
        """Returns (all_ok, list_of_warnings)"""
        warnings = []
        all_ok = True
        for t in targets:
            result = self.validate_target(t)
            if not result.allowed:
                all_ok = False
                warnings.append(f"BLOCKED {t}: {result.reason}")
            elif result.risk_level in ("high", "critical"):
                warnings.append(f"WARNING {t}: {result.reason}")

        # Metasploit requires explicit high-risk acknowledgement
        if "metasploit" in requested_tools:
            warnings.append(
                "WARNING: Metasploit exploitation tool selected — "
                "ensure explicit written authorisation exists."
            )
        return all_ok, warnings


# Singleton
guardrail_engine = GuardrailEngine()
