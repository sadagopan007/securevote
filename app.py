from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import random
import hashlib
import time
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hackathon-secret-2024")

# ── VOTER DATABASE (Voter ID → Aadhaar) ──────────────────────────────
VOTER_DATABASE = {
    "VOTER001": "123456789012",
    "VOTER002": "234567890123",
    "VOTER003": "345678901234",
    "VOTER004": "456789012345",
    "VOTER005": "567890123456",
    "VOTER006": "678901234567",
    "VOTER007": "789012345678",
    "VOTER008": "890123456789",
    "VOTER009": "901234567890",
    "VOTER010": "012345678901",
}

# ── IN-MEMORY STORAGE ─────────────────────────────────────────────────
otp_storage    = {}
votes          = {}
fraud_log      = []
login_attempts = {}
trust_score    = [100]

CANDIDATES = [
    {"id": "A", "name": "Arun Kumar",   "party": "Progressive Alliance", "symbol": "🌟"},
    {"id": "B", "name": "Bhavna Mehta", "party": "United Front",         "symbol": "🔥"},
    {"id": "C", "name": "Chetan Rao",   "party": "People's Party",       "symbol": "🌿"},
]

def generate_vote_hash(voter_id, candidate, timestamp):
    data = f"{voter_id}{candidate}{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16].upper()

def reduce_trust(amount=10):
    trust_score[0] = max(0, trust_score[0] - amount)

def get_results():
    counts = {c["id"]: 0 for c in CANDIDATES}
    for v in votes.values():
        counts[v["candidate"]] += 1
    return counts

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/send_otp", methods=["POST"])
def send_otp():
    voter_id = request.form.get("voter_id", "").strip().upper()
    aadhaar  = request.form.get("aadhaar", "").strip()

    if not voter_id or not aadhaar:
        return render_template("login.html", error="Please fill all fields.")

    if len(aadhaar) != 12 or not aadhaar.isdigit():
        return render_template("login.html", error="Aadhaar must be 12 digits.")

    if voter_id not in VOTER_DATABASE:
        fraud_log.append({"type": "unregistered_voter", "voter_id": voter_id, "time": time.time()})
        reduce_trust(10)
        return render_template("login.html",
            error="⚠ Voter ID not found in database. This attempt has been flagged.", alert=True)

    if VOTER_DATABASE[voter_id] != aadhaar:
        fraud_log.append({"type": "aadhaar_mismatch", "voter_id": voter_id, "time": time.time()})
        reduce_trust(10)
        return render_template("login.html",
            error="⚠ Aadhaar does not match records. This attempt has been flagged.", alert=True)

    if voter_id in votes:
        fraud_log.append({"type": "double_vote_attempt", "voter_id": voter_id, "time": time.time()})
        reduce_trust(10)
        return render_template("login.html",
            error="⚠ This Voter ID has already voted. Attempt flagged.", alert=True)

    attempts = login_attempts.get(voter_id, 0)
    if attempts >= 5:
        fraud_log.append({"type": "brute_force", "voter_id": voter_id, "time": time.time()})
        reduce_trust(15)
        return render_template("login.html",
            error="⚠ Too many attempts. Contact election office.", alert=True)

    otp = random.randint(100000, 999999)
    otp_storage[voter_id] = {"otp": otp, "aadhaar": aadhaar, "expires_at": time.time() + 300}
    login_attempts[voter_id] = attempts + 1

    print(f"\n{'='*40}\n  OTP for {voter_id}: {otp}\n{'='*40}\n")
    return render_template("otp.html", voter_id=voter_id, otp_demo=otp)

@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    voter_id    = request.form.get("voter_id", "").strip().upper()
    entered_otp = request.form.get("otp", "").strip()

    record = otp_storage.get(voter_id)
    if not record:
        return render_template("otp.html", voter_id=voter_id, error="Session expired. Start again.")

    if time.time() > record["expires_at"]:
        del otp_storage[voter_id]
        return render_template("login.html", error="OTP expired. Please login again.")

    if str(record["otp"]) != entered_otp:
        fraud_log.append({"type": "wrong_otp", "voter_id": voter_id, "time": time.time()})
        reduce_trust(5)
        return render_template("otp.html", voter_id=voter_id,
                               error="Wrong OTP. Try again.", otp_demo=record["otp"])

    session["voter_id"]      = voter_id
    session["authenticated"] = True
    return redirect(url_for("vote"))

@app.route("/vote")
def vote():
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    voter_id = session["voter_id"]
    if voter_id in votes:
        return redirect(url_for("success"))
    return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES)

@app.route("/cast_vote", methods=["POST"])
def cast_vote():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    voter_id  = session["voter_id"]
    candidate = request.form.get("candidate")

    if voter_id in votes:
        fraud_log.append({"type": "double_vote", "voter_id": voter_id, "time": time.time()})
        reduce_trust(10)
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Fraud detected! You already voted.")

    if candidate not in [c["id"] for c in CANDIDATES]:
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Invalid candidate selected.")

    timestamp = time.time()
    vote_hash = generate_vote_hash(voter_id, candidate, timestamp)
    votes[voter_id] = {"candidate": candidate, "timestamp": timestamp, "hash": vote_hash}

    session["vote_hash"] = vote_hash
    session["voted_for"] = candidate
    session.pop("authenticated", None)
    return redirect(url_for("success"))

@app.route("/success")
def success():
    candidate_id = session.get("voted_for")
    if not candidate_id:
        return redirect(url_for("login"))
    candidate = next((c for c in CANDIDATES if c["id"] == candidate_id), None)
    return render_template("success.html",
                           vote_hash=session.get("vote_hash", "N/A"),
                           candidate=candidate)

@app.route("/admin")
def admin():
    results     = get_results()
    total_votes = len(votes)
    results_with_names = [
        {**c, "votes": results[c["id"]],
         "pct": round(results[c["id"]] / total_votes * 100) if total_votes else 0}
        for c in CANDIDATES
    ]
    return render_template("admin.html",
                           candidates=results_with_names,
                           total_votes=total_votes,
                           trust_score=trust_score[0],
                           fraud_log=fraud_log[-10:],
                           votes=votes)

@app.route("/api/results")
def api_results():
    return jsonify({"results": get_results(), "total": len(votes),
                    "trust_score": trust_score[0], "fraud_events": len(fraud_log)})

@app.route("/reset")
def reset():
    votes.clear()
    otp_storage.clear()
    fraud_log.clear()
    login_attempts.clear()
    trust_score[0] = 100
    return redirect(url_for("admin"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
