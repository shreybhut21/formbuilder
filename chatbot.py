import json
import os
import re
import string
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
import joblib


class Chatbot:
    def __init__(self, model_path='chatbot_model.pkl', training_data_path='chatbot_training_data.json'):
        self.model_path = model_path
        self.training_data_path = training_data_path
        self.pipeline = None
        self.intents = {}
        if os.path.exists(self.model_path) and os.path.exists(self.training_data_path):
            self.load_model()
        else:
            self.train_model()

    def preprocess_text(self, text):
        text = text.lower()
        text = re.sub(r'\d+', '', text)
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = text.strip()
        return text

    def load_training_data(self):
        with open(self.training_data_path, 'r') as f:
            data = json.load(f)
        self.intents = data.get('intents', {})
        texts = []
        labels = []
        for intent, intent_data in self.intents.items():
            for pattern in intent_data.get('patterns', []):
                texts.append(self.preprocess_text(pattern))
                labels.append(intent)
        return texts, labels

    def train_model(self):
        texts, labels = self.load_training_data()
        self.pipeline = Pipeline([
            ('vectorizer', TfidfVectorizer(ngram_range=(1, 2), stop_words='english')),
            ('classifier', MultinomialNB())
        ])
        self.pipeline.fit(texts, labels)
        self.save_model()

    def save_model(self):
        joblib.dump(self.pipeline, self.model_path)

    def load_model(self):
        try:
            self.pipeline = joblib.load(self.model_path)
            with open(self.training_data_path, 'r') as f:
                data = json.load(f)
            self.intents = data.get('intents', {})
        except Exception as e:
            print(f"Model load failed: {e}")
            self.train_model()

    def predict_intent(self, message, threshold=0.2):
        if not self.pipeline:
            return None
        message = self.preprocess_text(message)
        probs = self.pipeline.predict_proba([message])[0]
        best_index = probs.argmax()
        print(f"DEBUG: Intent probabilities: {probs}, best intent index: {best_index}, best prob: {probs[best_index]}")
        if probs[best_index] < threshold:
            print("DEBUG: Probability below threshold, returning None")
            return None
        return self.pipeline.classes_[best_index]
            
    def get_response(self, message):
        intent = self.predict_intent(message)
        if not intent or intent not in self.intents:
            return "Sorry, I didn't understand that. Can you please rephrase?"
        responses = self.intents[intent].get('responses', [])
        if not responses:
            return "Sorry, I don't have a response for that."
        response = random.choice(responses)
        self.log_conversation(message, response)
        return response

    def log_conversation(self, user_msg, bot_msg):
        with open("chat_log.txt", "a") as f:
            f.write(f"User: {user_msg}\nBot: {bot_msg}\n\n")

    def add_intent(self, intent_name, patterns, responses):
        self.intents[intent_name] = {
            "patterns": patterns,
            "responses": responses
        }
        with open(self.training_data_path, 'w') as f:
            json.dump({"intents": self.intents}, f, indent=4)
        self.train_model()


# --------------------------------------
# Expanded training data with more intents and patterns
# --------------------------------------
sample_training_data = {
    "intents": {
        "greeting": {
            "patterns": ["hello", "hi", "hey", "good morning", "good evening", "howdy", "hey there"],
            "responses": ["Hello! How can I help you today?", "Hi there! What can I do for you?"]
        },
        "product_info": {
            "patterns": ["product", "feature", "pricing", "offer", "trial", "plans", "cost", "subscription"],
            "responses": ["We offer feature-rich form building tools. Check out our Products page."]
        },
        "form_help": {
            "patterns": ["create form", "how to make form", "edit form", "share form", "submit form", "form builder", "form templates"],
            "responses": ["You can create or customize forms easily from your dashboard."]
        },
        "account_help": {
            "patterns": ["login", "sign up", "account settings", "profile update", "change password", "forgot password", "reset password"],
            "responses": ["Go to your profile settings to manage your account, change password, etc."]
        },
        "thanks": {
            "patterns": ["thank you", "thanks", "thx", "ty", "thank you very much"],
            "responses": ["You're welcome!", "Happy to help!", "Anytime!"]
        },
        "next_steps": {
            "patterns": ["what now", "next step", "what to do", "then what", "what should i do next"],
            "responses": ["You can start by creating a form or browsing templates."]
        },
        "about": {
            "patterns": ["who are you", "about this", "what is formbuilder", "what is this website", "tell me about you"],
            "responses": ["FormBuilder Pro is your all-in-one solution for online form creation and management."]
        },
        "help_contact": {
            "patterns": ["help", "support", "contact", "phone number", "email support", "customer service", "contact us"],
            "responses": ["You can reach us at support@formbuilderpro.com or call +1-800-123-4567."]
        },
        "form_suggestion": {
            "patterns": ["need form for", "want form for", "suggest form for", "form for", "help me create form for"],
            "responses": ["Try adding fields like name, email, checkbox, dropdown, and date."]
        },
        "data_view": {
            "patterns": ["view data", "download csv", "see stats", "form responses", "view submissions", "export data"],
            "responses": ["Go to the dashboard to view submissions, download data or export stats."]
        },
        "form_sharing": {
            "patterns": ["share form", "how to share form", "send form", "form sharing"],
            "responses": ["You can share your forms via link or email from your dashboard."]
        },
        "form_deletion": {
            "patterns": ["delete form", "remove form", "erase form"],
            "responses": ["You can delete forms from your dashboard. Be careful, this action is irreversible."]
        },
        "form_editing": {
            "patterns": ["edit form", "change form", "update form"],
            "responses": ["You can edit your forms anytime from the form builder page."]
        }
    }
}

# Save training data once
if not os.path.exists('chatbot_training_data.json'):
    with open('chatbot_training_data.json', 'w') as f:
        json.dump(sample_training_data, f, indent=4)
    
# CLI testing (optional)
if __name__ == '__main__':
    bot = Chatbot()
    print("🤖 FormBuilder Pro Assistant (type 'exit' to quit)")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            print("Bot: Goodbye!")
            break
        print("Bot:", bot.get_response(user_input))
