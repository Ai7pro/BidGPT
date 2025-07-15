from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
import os
from email.message import EmailMessage
import smtplib

app = Flask(__name__, 
    static_folder='static',
    static_url_path='')  # This makes static files available at root URL
CORS(app)

# Load and parse knowledge base
def load_knowledge_base(path='knowledge_base.txt'):
    entries = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                entries.append(line.strip())
    return entries

kb_entries = load_knowledge_base()
vectorizer = TfidfVectorizer().fit(kb_entries)

# Get API key from environment variable (works with both local .env and Render.com)
api_key = os.getenv('GROQ_API_KEY')
if not api_key:
    raise ValueError("GROQ_API_KEY environment variable is not set")

# Groq client
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=api_key
)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    if not user_message:
        return jsonify({'response': 'Please ask a question.'})

    # Find most relevant KB entry
    user_vec = vectorizer.transform([user_message])
    kb_vecs = vectorizer.transform(kb_entries)
    sims = cosine_similarity(user_vec, kb_vecs)[0]
    idx = sims.argmax()
    context = kb_entries[idx] if sims[idx] > 0.2 else ""

    # Compose prompt for LLM
    system_prompt = (
        f"You are BidGPT. Always be concise. You are an expert in tender and bid related queries. Be professional.Use the following knowledge base.\n"
        f"Knowledge base: {context}\n"
        f"User question: {user_message}"
    )

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )
    answer = completion.choices[0].message.content
    return jsonify({'response': answer})

# Serve static files (frontend)
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    rating = data.get('rating')
    feedback_text = data.get('feedback')

    # Prepare email
    gmail_user = os.getenv('FEEDBACK_GMAIL_USER')
    gmail_pass = os.getenv('FEEDBACK_GMAIL_PASS')
    to_email = os.getenv('FEEDBACK_GMAIL_TO', gmail_user)

    if not (gmail_user and gmail_pass and to_email):
        return jsonify({'success': False, 'error': 'Email credentials not set'}), 500

    msg = EmailMessage()
    msg['Subject'] = f"BidGPT Feedback - Rating: {rating}"
    msg['From'] = gmail_user
    msg['To'] = to_email
    msg.set_content(f"Rating: {rating}\nFeedback: {feedback_text}")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__' and not os.environ.get('RENDER'):
    port = int(os.getenv('PORT', 5000))
    debug = True
    app.run(host='0.0.0.0', port=port, debug=debug)