import json, os
class Translator:
    def __init__(self, lang='en', locales_dir=None, fallback='en'):
        self.lang = lang
        self.locales_dir = locales_dir or os.path.join(os.path.dirname(__file__), 'locales')
        self.fallback = fallback
        self.translations = {}
        self.fallback_translations = {}
        self.load_language(self.lang)
        if self.fallback != self.lang:
            self.load_fallback()

    def load_language(self, lang):
        self.lang = lang
        path = os.path.join(self.locales_dir, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
        except Exception:
            self.translations = {}

    def load_fallback(self):
        path = os.path.join(self.locales_dir, f"{self.fallback}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.fallback_translations = json.load(f)
        except Exception:
            self.fallback_translations = {}

    def t(self, key):
        if key in self.translations:
            return self.translations[key]
        if key in self.fallback_translations:
            return self.fallback_translations[key]
        return key

    def available_languages(self):
        langs = []
        try:
            for fname in os.listdir(self.locales_dir):
                if fname.endswith('.json'):
                    langs.append(os.path.splitext(fname)[0])
        except Exception:
            pass
        return sorted(langs)
