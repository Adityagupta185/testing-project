"""
Payment Service — v2.3.x

Card charge processing with Luhn validation, BIN-based network detection,
fraud velocity checks, and transaction lifecycle management.

Architecture modelled after:
  github.com/GoogleCloudPlatform/microservices-demo (paymentservice)

v2.3.1 regression: PCI-DSS audit logging was added as an in-memory list
with no eviction policy. Under load this causes heap exhaustion.
"""

import os
import re
import uuid
import time
import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("payment-service")

VERSION    = os.getenv("APP_VERSION", "2.3.1")
START_TIME = time.time()

# ── In-memory stores (production: Redis + Postgres) ───────────────────────────
_transactions: dict       = {}
_velocity:     dict       = defaultdict(list)   # card_hash → [unix timestamps]
_audit_log:    list       = []                  # v2.3.1 regression — unbounded


# ── Card validation (ISO/IEC 7812) ────────────────────────────────────────────

CARD_PATTERNS = {
    "Visa":       re.compile(r"^4[0-9]{12}(?:[0-9]{3,6})?$"),
    "Mastercard": re.compile(r"^5[1-5][0-9]{14}$|^2(?:2[2-9][1-9]|[3-6]\d{2}|7[01]\d|720)\d{12}$"),
    "Amex":       re.compile(r"^3[47][0-9]{13}$"),
    "Discover":   re.compile(r"^6(?:011|5[0-9]{2})[0-9]{12}$"),
    "JCB":        re.compile(r"^35(?:2[89]|[3-8][0-9])[0-9]{12}$"),
    "UnionPay":   re.compile(r"^62[0-9]{14,17}$"),
}

CVV_LENGTHS = {"Amex": {4}, "default": {3}}

SUPPORTED_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "SGD", "INR", "BRL",
}

MAX_AMOUNT        = 50_000.00
VELOCITY_WINDOW   = 3600   # seconds — 1 hour sliding window
VELOCITY_MAX_TXN  = 10     # max transactions per card per hour


def luhn_check(number: str) -> bool:
    """Luhn algorithm — validates card checksum (same as Stripe, Adyen, Square)."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def detect_network(number: str) -> str:
    clean = re.sub(r"[\s-]", "", number)
    for name, pattern in CARD_PATTERNS.items():
        if pattern.match(clean):
            return name
    return "Unknown"


def validate_expiry(month: int, year: int) -> bool:
    if not (1 <= month <= 12):
        return False
    now = datetime.now(timezone.utc)
    # Card is valid through end of the expiry month
    return (year, month) >= (now.year, now.month)


# ── Fraud detection ───────────────────────────────────────────────────────────

def velocity_check(card_hash: str) -> tuple:
    now    = time.time()
    cutoff = now - VELOCITY_WINDOW
    _velocity[card_hash] = [t for t in _velocity[card_hash] if t > cutoff]
    count = len(_velocity[card_hash])
    if count >= VELOCITY_MAX_TXN:
        return False, f"velocity_exceeded ({count} txn in last hour)"
    return True, ""


def risk_score(amount: float, network: str, card_hash: str) -> float:
    score = 0.0
    if amount > 5_000:  score += 0.30
    elif amount > 1_000: score += 0.10
    score += min(len(_velocity.get(card_hash, [])) * 0.05, 0.40)
    if network == "Unknown": score += 0.30
    return min(round(score, 2), 1.0)


# ── v2.3.1 regression: in-memory PCI audit log ───────────────────────────────

def _audit(txn: dict, req) -> None:
    """
    v2.3.1: Added for PCI-DSS v4.0 audit trail (Req-10: log all access to CHD).
    Should write to Cloud Logging / Pub/Sub — instead appends to a module-level
    list with no size cap or TTL. Under sustained traffic this exhausts heap.
    """
    _audit_log.append({
        "transaction_id": txn["transaction_id"],
        "amount":         txn["amount"],
        "currency":       txn["currency"],
        "card_network":   txn["card_network"],
        "card_last4":     txn["card_last4"],
        "status":         txn["status"],
        "risk_score":     txn["risk_score"],
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "request_ip":     req.remote_addr,
        "user_agent":     req.headers.get("User-Agent", ""),
        "compliance": {
            "pci_version":    "PCI-DSS-v4.0",
            "controls":       ["req-3", "req-4", "req-10"],
            "data_retention": "7-years",
            "raw_headers":    dict(req.headers),            # large per-request blob
            "checksum":       hashlib.sha256(               # full txn hash
                str(txn).encode()
            ).hexdigest(),
            "reserved":       "X" * 4096,                  # "future regulatory fields"
        },
    })


# ── Charge logic ──────────────────────────────────────────────────────────────

def _charge(payload: dict, req):
    card_number  = re.sub(r"[\s-]", "", str(payload.get("card_number", "")))
    expiry_month = int(payload.get("expiry_month", 0))
    expiry_year  = int(payload.get("expiry_year",  0))
    cvv          = str(payload.get("cvv", ""))
    amount       = float(payload.get("amount", 0))
    currency     = str(payload.get("currency", "USD")).upper()
    merchant_id  = str(payload.get("merchant_id", "unknown"))

    # --- validations ----------------------------------------------------------
    if not luhn_check(card_number):
        return {"error": "invalid_card", "message": "Card number failed Luhn check"}, 422

    network = detect_network(card_number)

    expected_cvv = CVV_LENGTHS.get(network, CVV_LENGTHS["default"])
    if len(cvv) not in expected_cvv:
        return {"error": "invalid_cvv",
                "message": f"CVV must be {expected_cvv} digits for {network}"}, 422

    if not validate_expiry(expiry_month, expiry_year):
        return {"error": "card_expired", "message": "Card has expired"}, 422

    if not (0 < amount <= MAX_AMOUNT):
        return {"error": "invalid_amount",
                "message": f"Amount must be between $0.01 and ${MAX_AMOUNT:,.2f}"}, 422

    if currency not in SUPPORTED_CURRENCIES:
        return {"error": "unsupported_currency",
                "message": f"{currency} is not supported"}, 422

    card_hash = hashlib.sha256(card_number.encode()).hexdigest()[:16]

    ok, reason = velocity_check(card_hash)
    if not ok:
        return {"error": "transaction_declined", "decline_code": reason}, 402

    risk = risk_score(amount, network, card_hash)
    if risk >= 0.90:
        return {"error": "transaction_declined", "decline_code": "high_risk"}, 402

    # --- record ---------------------------------------------------------------
    _velocity[card_hash].append(time.time())

    txn = {
        "transaction_id": f"txn_{uuid.uuid4().hex}",
        "status":         "captured",
        "amount":         amount,
        "currency":       currency,
        "card_network":   network,
        "card_last4":     card_number[-4:],
        "merchant_id":    merchant_id,
        "risk_score":     risk,
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }
    _transactions[txn["transaction_id"]] = txn

    # v2.3.1 regression
    if VERSION == "2.3.1":
        _audit(txn, req)
        logger.warning(
            f"[v2.3.1] audit_log size={len(_audit_log)} entries "
            f"≈ {len(_audit_log) * 5:.0f} KB — heap growing"
        )

    logger.info(
        f"charge captured | txn={txn['transaction_id']} "
        f"amount={amount}{currency} network={network} "
        f"risk={risk} merchant={merchant_id}"
    )
    return txn, 200


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status":          "ok",
        "version":         VERSION,
        "uptime_seconds":  int(time.time() - START_TIME),
        "transactions":    len(_transactions),
        "audit_log_size":  len(_audit_log),
    })


@app.route("/charge", methods=["POST"])
def charge_endpoint():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid_request", "message": "JSON body required"}), 400
    result, status = _charge(payload, request)
    return jsonify(result), status


@app.route("/transactions", methods=["GET"])
def list_transactions():
    page     = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("per_page", 20)), 100)
    items    = sorted(_transactions.values(), key=lambda x: x["created_at"], reverse=True)
    start    = (page - 1) * per_page
    return jsonify({
        "transactions": items[start : start + per_page],
        "total":        len(items),
        "page":         page,
        "per_page":     per_page,
    })


@app.route("/transactions/<txn_id>")
def get_transaction(txn_id):
    txn = _transactions.get(txn_id)
    if not txn:
        return jsonify({"error": "not_found"}), 404
    return jsonify(txn)


@app.route("/refund/<txn_id>", methods=["POST"])
def refund(txn_id):
    txn = _transactions.get(txn_id)
    if not txn:
        return jsonify({"error": "not_found"}), 404
    if txn["status"] != "captured":
        return jsonify({"error": "not_refundable", "current_status": txn["status"]}), 422
    txn["status"]      = "refunded"
    txn["refunded_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"refund ok | txn={txn_id}")
    return jsonify(txn)


@app.route("/metrics")
def metrics():
    statuses = defaultdict(int)
    for t in _transactions.values():
        statuses[t["status"]] += 1
    return jsonify({
        "version":            VERSION,
        "uptime_seconds":     int(time.time() - START_TIME),
        "total_transactions": len(_transactions),
        **statuses,
        "audit_log_entries":  len(_audit_log),
        "audit_log_size_kb":  round(len(_audit_log) * 5.2, 1),
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Payment Service {VERSION} starting on :{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
