from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import random
import hashlib
import time
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hackathon-secret-2024")

# In-memory storage (fine for demo)
otp_storage = {}       # voter_id -> {otp, expires_at, aadhaar}
votes = {}             # voter_id -> {candidate, timestamp, hash}
fraud_log = []         # list of fraud events
login_attempts = {}    # voter_id -> attempt count

CANDIDATES = [
    {"id": "A", "name": "Arun Kumar",   "party": "Progressive Alliance",  "symbol": "🌟"},
    {"id": "B", "name": "Bhavna Mehta", "party": "United Front",          "symbol": "🔥"},
    {"id": "C", "name": "Chetan Rao",   "party": "People's Party",        "symbol": "🌿"},
]

def generate_vote_hash(voter_id, candidate, timestamp):
    data = f"{voter_id}{candidate}{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16].upper()

def calculate_trust_score():
    score = 100
    fraud_penalty = len(fraud_log) * 5
    score -= fraud_penalty
    return max(0, min(100, score))

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

    if voter_id in votes:
        fraud_log.append({"type": "double_vote_attempt", "voter_id": voter_id, "time": time.time()})
        return render_template("login.html", error="This Voter ID has already voted.")

    attempts = login_attempts.get(voter_id, 0)
    if attempts >= 5:
        fraud_log.append({"type": "brute_force", "voter_id": voter_id, "time": time.time()})
        return render_template("login.html", error="Too many attempts. Contact election office.")

    otp = random.randint(100000, 999999)
    otp_storage[voter_id] = {
        "otp": otp,
        "aadhaar": aadhaar,
        "expires_at": time.time() + 300  # 5 min expiry
    }
    login_attempts[voter_id] = attempts + 1

    print(f"\n{'='*40}")
    print(f"  OTP for {voter_id}: {otp}")
    print(f"{'='*40}\n")

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
        return render_template("otp.html", voter_id=voter_id, error="Wrong OTP. Try again.", otp_demo=record["otp"])

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
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Fraud detected! You already voted.")

    if candidate not in [c["id"] for c in CANDIDATES]:
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Invalid candidate selected.")

    timestamp = time.time()
    vote_hash = generate_vote_hash(voter_id, candidate, timestamp)

    votes[voter_id] = {
        "candidate": candidate,
        "timestamp": timestamp,
        "hash":      vote_hash
    }

    session["vote_hash"] = vote_hash
    session["voted_for"] = candidate
    return redirect(url_for("success"))

@app.route("/success")
def success():
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    candidate_id = session.get("voted_for", "?")
    candidate    = next((c for c in CANDIDATES if c["id"] == candidate_id), None)
    return render_template("success.html",
                           vote_hash=session.get("vote_hash", "N/A"),
                           candidate=candidate)

@app.route("/admin")
def admin():
    results     = get_results()
    trust_score = calculate_trust_score()
    total_votes = len(votes)
    results_with_names = [
        {**c, "votes": results[c["id"]],
         "pct": round(results[c["id"]] / total_votes * 100) if total_votes else 0}
        for c in CANDIDATES
    ]
    return render_template("admin.html",
                           candidates=results_with_names,
                           total_votes=total_votes,
                           trust_score=trust_score,
                           fraud_log=fraud_log[-10:],
                           votes=votes)

@app.route("/api/results")
def api_results():
    return jsonify({
        "results":      get_results(),
        "total":        len(votes),
        "trust_score":  calculate_trust_score(),
        "fraud_events": len(fraud_log)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
