import os
from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Post
from better_profanity import profanity
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mindspace.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "mindspace-dev-secret")

db.init_app(app)

# Initialise NLP tools once at startup
profanity.load_censor_words()
analyzer = SentimentIntensityAnalyzer()

# Additional rule-based checks beyond the profanity library
BANNED_SYMBOLS = ["@"]


def moderate_and_analyze(text: str):
    """
    Two-step pipeline:
      1. Rule-based filter  – profanity library + symbol/keyword rules
      2. Sentiment analysis – VADER compound score → tag

    Returns (sentiment_tag, error_message).
    On failure, sentiment_tag is None and error_message explains the rejection.
    On success, error_message is None.
    """
    # ── Step 1 : Rule-based filter ────────────────────────────────────────────
    if profanity.contains_profanity(text):
        return None, (
            "Your post was flagged for inappropriate language and cannot be submitted."
        )

    for symbol in BANNED_SYMBOLS:
        if symbol in text:
            return None, (
                f"Posts may not contain the '{symbol}' symbol. "
                "Please revise and try again."
            )

    # ── Step 2 : Sentiment analysis ───────────────────────────────────────────
    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]

    if compound <= -0.5:
        tag = "Distressed"
    elif compound >= 0.5:
        tag = "Positive"
    else:
        tag = "Neutral"

    return tag, None


# ── Routes ────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    has_distressed = any(p.sentiment_tag == "Distressed" for p in posts)
    return render_template("index.html", posts=posts, has_distressed=has_distressed)


@app.route("/posts", methods=["POST"])
def create_post():
    content = request.form.get("content", "").strip()

    if not content:
        flash("Post content cannot be empty.", "error")
        return redirect(url_for("index"))

    if len(content) > 1000:
        flash("Posts must be 1 000 characters or fewer.", "error")
        return redirect(url_for("index"))

    sentiment_tag, error = moderate_and_analyze(content)

    if error:
        flash(error, "error")
        return redirect(url_for("index"))

    post = Post(content=content, sentiment_tag=sentiment_tag)
    db.session.add(post)
    db.session.commit()

    return redirect(url_for("index"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
